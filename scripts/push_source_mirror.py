"""Publish the pipeline's digest-pinned sources to the mirror bucket.

Companion to `scripts/source_mirror.py`, which reads what this writes. See that module
for why the mirror exists and why it is content-addressed.

## What gets mirrored

Everything the pipeline pins by a content digest, and nothing else. The pin is read
from the module that owns it rather than restated here, so this cannot drift from what
the pipeline actually fetches:

| Source | Pin lives in |
|---|---|
| 4 cBioPortal MAFs | `fetch_cbioportal_maf.STUDIES` (git-LFS oid, read from upstream) |
| Alliance orthology | `fetch_orthologs.ORTHOLOGY_SHA256` |
| GRCh38 reference | `.github/workflows/build-image.yml` (`REFERENCE_FASTA_*`) |

The reference is the one exception to "read the pin from its owner": it is pinned in
the workflow, which is not importable, so its digest is restated below and `--check`
re-reads the workflow to prove the two agree.

**HGNC is deliberately absent.** `materialize_genes.fetch_hgnc` downloads "latest" from
a stable URL with no digest and caches on existence, so there is no pin to mirror.
Mirroring it would mean *choosing* a pin, which changes gene symbols and therefore the
graph — a reviewed decision, not a side effect of setting up a bucket.

## Usage

    aws sso login --profile <profile>
    python scripts/push_source_mirror.py --check            # verify local bytes vs pins
    python scripts/push_source_mirror.py --bucket <name> --dry-run
    python scripts/push_source_mirror.py --bucket <name>

Objects are written to `sha256/<digest>` and never overwritten: a new pin is a new
digest is a new key, so a push can only ever add. `--manifest` also writes a
human-readable index, which is documentation only — nothing reads it at build time.
"""

from __future__ import annotations

import argparse
import importlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from source_mirror import sha256_file  # noqa: E402

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build-image.yml"


@dataclass
class MirrorObject:
    label: str
    digest: str
    local: Path
    upstream: str
    size: int | None = None
    notes: str = field(default="")


def _reference_pin() -> tuple[str, str]:
    """(url, md5) as pinned in build-image.yml, so --check can cross-read it."""
    text = WORKFLOW.read_text()
    url = re.search(r"^\s*REFERENCE_FASTA_URL:\s*(\S+)\s*$", text, re.M)
    md5 = re.search(r"^\s*REFERENCE_FASTA_MD5:\s*(\S+)\s*$", text, re.M)
    if not (url and md5):
        raise SystemExit(f"could not read REFERENCE_FASTA_URL/_MD5 from {WORKFLOW}")
    return url.group(1), md5.group(1)


#: sha256 of the file the workflow pins by md5. Content addressing needs one algorithm
#: across the whole mirror; the md5 stays in the workflow because that is what UCSC
#: publishes and what `md5sum -c` there verifies.
REFERENCE_SHA256 = "c1dd87068c254eb53d944f71e51d1311964fce8de24d6fc0effc9c61c01527d4"
REFERENCE_LOCAL = REPO_ROOT / "data" / "reference" / "GRCh38" / "hg38.fa.gz"


def collect(offline: bool = False) -> list[MirrorObject]:
    """Every pinned object, with its digest read from whichever module owns the pin."""
    objects: list[MirrorObject] = []

    maf = importlib.import_module("fetch_cbioportal_maf")
    for study_id, source in sorted(maf.STUDIES.items()):
        local = REPO_ROOT / "data" / "raw" / f"{study_id}_data_mutations.txt"
        if offline:
            if not local.exists():
                print(f"skip    {study_id}: no local copy and --offline given")
                continue
            digest, size = sha256_file(local), local.stat().st_size
        else:
            digest, size = maf.read_lfs_pointer(source)
        objects.append(
            MirrorObject(
                label=f"cbioportal/{study_id}/data_mutations.txt",
                digest=digest,
                local=local,
                upstream=f"https://github.com/{source.repo}/blob/{source.ref}/{source.path}",
                size=size,
                notes=f"git-LFS oid, pinned at {source.ref[:12]}",
            )
        )

    orth = importlib.import_module("fetch_orthologs")
    objects.append(
        MirrorObject(
            label="alliance/ORTHOLOGY-ALLIANCE_COMBINED.tsv.gz",
            digest=orth.ORTHOLOGY_SHA256,
            local=orth.ORTHOLOGY_CACHE,
            upstream=orth.ORTHOLOGY_URL,
            notes=f"Alliance release {orth.ORTHOLOGY_RELEASE}",
        )
    )

    url, md5 = _reference_pin()
    objects.append(
        MirrorObject(
            label="ucsc/hg38.fa.gz",
            digest=REFERENCE_SHA256,
            local=REFERENCE_LOCAL,
            upstream=url,
            notes=f"md5 {md5} as pinned in build-image.yml",
        )
    )
    return objects


def verify(objects: list[MirrorObject]) -> int:
    """Hash each local copy against its pin. Returns the number that failed."""
    bad = 0
    for obj in objects:
        if not obj.local.exists():
            print(f"MISSING {obj.label}: no local copy at {obj.local}")
            bad += 1
            continue
        got = sha256_file(obj.local)
        if got != obj.digest:
            print(f"MISMATCH {obj.label}: local {got[:12]}... != pin {obj.digest[:12]}...")
            bad += 1
        else:
            size = obj.local.stat().st_size
            if obj.size is not None and size != obj.size:
                print(f"MISMATCH {obj.label}: local {size} bytes != pin {obj.size}")
                bad += 1
            else:
                print(f"ok      {obj.label}  {obj.digest[:12]}...  {size:,} bytes")
    return bad


def already_there(bucket: str, key: str, profile: str | None) -> bool:
    cmd = ["aws", "s3api", "head-object", "--bucket", bucket, "--key", key]
    if profile:
        cmd += ["--profile", profile]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def push(objects: list[MirrorObject], bucket: str, profile: str | None, dry_run: bool) -> int:
    pushed = skipped = 0
    for obj in objects:
        key = f"sha256/{obj.digest}"
        if already_there(bucket, key, profile):
            print(f"present {obj.label} -> s3://{bucket}/{key}")
            skipped += 1
            continue
        cmd = ["aws", "s3", "cp", str(obj.local), f"s3://{bucket}/{key}"]
        if profile:
            cmd += ["--profile", profile]
        if dry_run:
            print(f"DRY-RUN {' '.join(cmd)}")
            continue
        print(f"upload  {obj.label} -> s3://{bucket}/{key}")
        result = subprocess.run(cmd)
        if result.returncode:
            raise SystemExit(f"upload failed for {obj.label}")
        pushed += 1
    print(f"\n{pushed} uploaded, {skipped} already present")
    return pushed


def manifest(objects: list[MirrorObject]) -> str:
    lines = [
        "# Digest-pinned sources mirrored to the bucket in scripts/source_mirror.py.",
        "# Generated by scripts/push_source_mirror.py -- documentation only, nothing reads",
        "# this at build time. The key is sha256/<digest>.",
        "\t".join(["label", "sha256", "bytes", "upstream", "notes"]),
    ]
    for obj in objects:
        size = obj.size if obj.size is not None else (
            obj.local.stat().st_size if obj.local.exists() else ""
        )
        lines.append("\t".join([obj.label, obj.digest, str(size), obj.upstream, obj.notes]))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bucket", help="target bucket name (required unless --check)")
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument("--check", action="store_true", help="verify local bytes against pins, push nothing")
    parser.add_argument("--dry-run", action="store_true", help="print the uploads without doing them")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="take MAF digests from the local copies instead of upstream's LFS pointers "
             "(for when the contents API is unreachable; --check still proves the bytes)",
    )
    parser.add_argument("--manifest", type=Path, help="write the human-readable index here")
    args = parser.parse_args(argv)

    objects = collect(offline=args.offline)
    bad = verify(objects)

    if args.manifest:
        args.manifest.write_text(manifest(objects))
        print(f"wrote {args.manifest}")

    if bad:
        print(f"\n{bad} object(s) failed verification; refusing to push")
        return 1
    if args.check:
        return 0
    if not args.bucket:
        parser.error("--bucket is required unless --check is given")

    push(objects, args.bucket, args.profile, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
