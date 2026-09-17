"""Fetch a cBioPortal study's MAF (`data_mutations.txt`) for the variant layer.

Part of the variant layer PoC (nf-osi/kg-pipeline#95). See `docs/variant-layer.md`.

## Why this is not just a `curl`

cBioPortal study files live in git-LFS-backed datahub repos, so the path that looks like
a file (`public/<study>/data_mutations.txt`) actually serves a ~130-byte LFS *pointer*.
Getting the bytes means: read the pointer, extract `oid`/`size`, ask the repo's LFS
batch endpoint for a signed URL, then download that. `git clone` would drag the whole
multi-GB datahub along, so the batch API is used directly.

## Pin to a commit, not a branch

cBioPortal **reprocesses studies in place**. A branch ref therefore does not identify
the bytes: re-fetch later and you may get a different file under the same name. Two
measurements from 2026-09-16 make it concrete:

* `schw_ctf_synodos_2025` at upstream `master` is the genome-nexus / `isoform: mskcc`
  rewrite -- 57 columns with **no `Gene` (ENSG) and no `HGNC_ID`**, only `Hugo_Symbol`
  and `Entrez_Gene_Id`. Gene nodes are keyed on HGNC and the symbol is explicitly not a
  safe key, so that form is unusable here.
* The same study's tarball and git copies, both "current", differ on 98 `Hugo_Symbol`
  values (`DDX58`/`RIGI`, `KIAA0100`/`BLTP2`, ...). Same variants, drifting symbols.

So each study pins a **commit SHA**, and a commit names an LFS `oid`, which is a content
digest. That is reproducible in a way no branch or "latest" URL is.

For the three CTF/Synodos studies the **add-commit** is the one to take: it holds the
original NF-OSI 114-column submission, before reprocessing. For `nfib_ctf_biobank_2025`
it is the *only* usable ref -- the object `master` names 404s, while the add-commit's
object is live.

`nst_nfosi_ntap` is the exception that shows the add-commit is a heuristic, not a rule:
it was added holding a 955-row / 19-sample release and only grew to the full 23,741 rows
over 80 samples nearly two years later. The two share no barcodes, so its pin is the
later revision, and `min_rows` is what stops the small one being taken by mistake.

## Sources considered

| Source | Status |
|---|---|
| `cBioPortal/datahub` @ a pinned commit | **Used for every study.** Full 113/114-column MAF: `Consequence` (SO terms), `HGVSc`/`HGVSp`, `Gene`, `HGNC_ID`. |
| `nf-osi/datahub` fork | **No longer used.** It held bytes identical to upstream for the studies it carried (same LFS oids), and its `master` last synced 2025-01 so it never carried the 2025-26 studies at all. Pinning upstream retired it. |
| `datahub.assets.cbioportal.org/<study>.tar.gz` | **Rejected.** Unversioned "latest": no commit, no digest, contents change under you. It also ships whatever form is current, which for `schw` is the 57-column one, and for `nst_nfosi_ntap` is a gnomAD-filtered re-release (955 rows / 19 samples vs 23,741 / 80, with renamed barcodes sharing not one sample with the crosswalk). |
| cBioPortal REST API | Current and needs no LFS, but drops `Consequence`, `HGVSc`, `HGVSp`, `HGNC_ID` and gnomAD AF. Documented fallback, not implemented. |

Adding a study is a `STUDIES` entry: find the commit that added it, take that SHA.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GITHUB_API = "https://api.github.com"
USER_AGENT = "nf-osi-kg-pipeline/fetch_cbioportal_maf"


#: Columns every downstream step needs, whichever source the MAF came from.
#: `Gene` and `HGNC_ID` are the two gene-identity columns -- `materialize_genes.py`
#: raises without `Gene`, and gene NODES are keyed on HGNC -- and cBioPortal's
#: genome-nexus release of a study drops both. That is the whole reason a study can need
#: reprocessed copy of a study unusable here, hence the pinned commits below.
REQUIRED_COLUMNS = frozenset({"Gene", "HGNC_ID", "Hugo_Symbol", "Tumor_Sample_Barcode"})


@dataclass(frozen=True)
class StudySource:
    """Where a study's MAF lives, pinned to an immutable commit."""

    study_id: str
    repo: str
    path: str
    #: A COMMIT SHA, not a branch. The bytes behind a branch change under you:
    #: cBioPortal reprocesses studies in place, and two concurrently-published copies
    #: of `schw_ctf_synodos_2025` already differ on 98 `Hugo_Symbol` values. A commit
    #: names an LFS oid, which is a content digest, so the pin is reproducible.
    ref: str
    #: Assembly the MAF declares, asserted against the seqmap by `vrsify maf`.
    assembly: str = "GRCh38"
    #: Tripwire for a careless re-pin: reject a MAF with fewer data rows than this.
    min_rows: int = 0


STUDIES: dict[str, StudySource] = {
    # The three CTF/Synodos studies are pinned to the upstream commit that ADDED them.
    # That matters: cBioPortal later reprocesses studies in place with genome-nexus,
    # which rewrites the MAF to a 57-column form with no `Gene` and no `HGNC_ID`, and
    # for `nfib` the reprocessed LFS object is missing from the server entirely. The
    # add-commit still names the original 114-column submission, and its LFS object is
    # live.
    "nfib_ctf_biobank_2025": StudySource(
        study_id="nfib_ctf_biobank_2025",
        repo="cBioPortal/datahub",
        path="public/nfib_ctf_biobank_2025/data_mutations.txt",
        ref="3ffe91da5a18e6ff73f8a1c1e8b4f12df41442f4",  # Add nfib ctf biobank (#2234)
        min_rows=600_000,
    ),
    "lgg_ctf_synodos_2025": StudySource(
        study_id="lgg_ctf_synodos_2025",
        repo="cBioPortal/datahub",
        path="public/lgg_ctf_synodos_2025/data_mutations.txt",
        ref="d84cab37f035d2e89dbe54a60f64349de549e9e3",  # Add lgg ctf synodos (#2231)
        min_rows=30_000,
    ),
    # Same bytes as the nf-osi fork's unmerged `add-schw-ctf-synodos` branch (identical
    # LFS oid 103448718d...), so pinning here drops that fork-branch dependency.
    "schw_ctf_synodos_2025": StudySource(
        study_id="schw_ctf_synodos_2025",
        repo="cBioPortal/datahub",
        path="public/schw_ctf_synodos_2025/data_mutations.txt",
        ref="1cc0ead234b732b08964623ed95c9a560b4c92c6",  # Add new CTF Synodos (#2138)
        min_rows=40_000,
    ),
    # NOT the commit that added this study: it was added (as `nst_nfosi_2022`) holding
    # a 955-row / 19-sample release, and only grew to the full 23,741 rows over 80
    # samples in Dec 2024. Those two releases share not a single barcode, so the
    # add-commit heuristic that is right for the studies above is wrong here -- hence
    # min_rows, which rejects the small one outright.
    #
    # Pinned to the Jan 2026 revision rather than the byte-identical-to-previous Dec
    # 2024 one (`45dcc57fb4007480207102cf48645c08c0c378ec`): they differ only in 24
    # `Hugo_Symbol` cells refreshed to current HGNC names, with every `HGNC_ID` and
    # `Gene` unchanged, so nothing the graph keys on moves.
    "nst_nfosi_ntap": StudySource(
        study_id="nst_nfosi_ntap",
        repo="cBioPortal/datahub",
        path="public/nst_nfosi_ntap/data_mutations.txt",
        ref="86690e1ed9752b1dcd50b5657f5f05eafa4b6b78",  # Gene Table v7 (#2252)
        min_rows=20_000,
    ),
}



def _request(url: str, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=120)


def _github_headers() -> dict:
    """Authenticate when a token is around, purely to dodge the 60/hr anonymous limit."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def read_lfs_pointer(source: StudySource) -> tuple[str, int]:
    """Return the (oid, size) an LFS pointer declares for the study's MAF."""
    url = f"{GITHUB_API}/repos/{source.repo}/contents/{source.path}?ref={source.ref}"
    with _request(url, headers={"Accept": "application/vnd.github+json", **_github_headers()}) as resp:
        meta = json.load(resp)
    if not meta.get("content"):
        raise SystemExit(
            f"{source.repo}/{source.path}: no inline content in the contents API response. "
            "The file is probably too large to be a pointer, i.e. not LFS-backed."
        )
    pointer = base64.b64decode(meta["content"]).decode("utf-8", "replace")
    oid = re.search(r"^oid sha256:([0-9a-f]{64})$", pointer, re.M)
    size = re.search(r"^size (\d+)$", pointer, re.M)
    if not (oid and size):
        raise SystemExit(
            f"{source.repo}/{source.path} is not a git-LFS pointer. First bytes:\n"
            f"{pointer[:200]}"
        )
    return oid.group(1), int(size.group(1))


def resolve_lfs_download(source: StudySource, oid: str, size: int) -> str:
    """Ask the repo's LFS batch endpoint for a signed download URL."""
    payload = json.dumps(
        {
            "operation": "download",
            "transfers": ["basic"],
            "objects": [{"oid": oid, "size": size}],
        }
    ).encode()
    url = f"https://github.com/{source.repo}.git/info/lfs/objects/batch"
    with _request(
        url,
        data=payload,
        headers={
            "Accept": "application/vnd.git-lfs+json",
            "Content-Type": "application/vnd.git-lfs+json",
        },
    ) as resp:
        batch = json.load(resp)
    obj = batch["objects"][0]
    if "error" in obj:
        # This is exactly how upstream cBioPortal/datahub fails. Say so, rather than
        # letting a KeyError imply a bug here.
        raise SystemExit(
            f"LFS object {oid[:12]}... unavailable from {source.repo}: "
            f"{obj['error'].get('message')} (code {obj['error'].get('code')}). "
            "The repo lists the file but does not host its LFS bytes."
        )
    return obj["actions"]["download"]["href"]


def sha256_file(path: Path) -> str:
    """Hash a MAF without loading the whole file into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_size: int, expected_oid: str) -> None:
    """Publish downloaded bytes only after verifying the pinned LFS identity."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=destination.name + ".", suffix=".part", delete=False
    ) as out:
        tmp = Path(out.name)
        try:
            written = 0
            digest = hashlib.sha256()
            with _request(url) as resp:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
            if written != expected_size:
                raise SystemExit(
                    f"short read: got {written} bytes, pointer declared {expected_size}"
                )
            if digest.hexdigest() != expected_oid:
                raise SystemExit("SHA-256 mismatch: downloaded MAF does not match pinned LFS oid")
            out.close()
            tmp.chmod(destination.stat().st_mode & 0o777 if destination.exists() else 0o644)
            tmp.replace(destination)
        finally:
            tmp.unlink(missing_ok=True)


def maf_header(path: Path) -> list[str]:
    """Column names of a MAF, skipping the `#` banner lines cBioPortal writes."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("#"):
                return line.rstrip("\n").split("\t")
    return []


def count_rows(path: Path) -> int:
    """Data rows, i.e. excluding `#` banners and the header."""
    with open(path, "rb") as handle:
        return max(sum(1 for line in handle if not line.startswith(b"#")) - 1, 0)


def accept_candidate(path: Path, source: StudySource) -> str:
    """Return "" if this file is usable for ``source``, else why it is not.

    Two independent checks, because they catch different failures. Columns catch the
    genome-nexus release, which is the same variants with the gene identifiers stripped
    out. Row count catches a *filtered re-release*, which has every column but is a
    different, smaller dataset wearing the same study id.
    """
    missing = sorted(REQUIRED_COLUMNS - set(maf_header(path)))
    if missing:
        return f"missing required column(s) {missing}"
    rows = count_rows(path)
    if source.min_rows and rows < source.min_rows:
        return f"{rows} data rows, fewer than the {source.min_rows} expected"
    return ""


def fetch_maf(study_id: str, destination: Path, force: bool = False) -> Path:
    """Download ``study_id``'s MAF to ``destination``, reusing a cached copy.

    Cached and downloaded bytes must match the pinned LFS SHA-256 digest. The file
    must also pass `accept_candidate`, so a source that has been rewritten into a
    poorer form fails the run instead of quietly shrinking the graph.
    """
    source = STUDIES.get(study_id)
    if source is None:
        raise SystemExit(
            f"unknown study {study_id!r}; known: {', '.join(sorted(STUDIES))}. "
            "Add a STUDIES entry to fetch a new one."
        )

    oid, size = read_lfs_pointer(source)
    # Schema and row counts do not identify a revision: old annotations can pass
    # both, even at the same byte size. Verify the bytes against the current pin.
    if destination.exists() and not force:
        if destination.stat().st_size != size:
            reason = f"has {destination.stat().st_size} bytes, expected {size}"
        elif sha256_file(destination) != oid:
            reason = "SHA-256 does not match pinned LFS oid"
        else:
            reason = accept_candidate(destination, source)
        if not reason:
            print(f"cached  {destination} ({destination.stat().st_size} bytes)")
            return destination
        print(f"re-fetching {destination}: cached copy {reason}")

    url = resolve_lfs_download(source, oid, size)
    print(
        f"fetching {source.repo}/{source.path}@{source.ref[:12]} "
        f"-> {destination} ({size} bytes, oid {oid[:12]}...)"
    )
    download(url, destination, size, oid)
    reason = accept_candidate(destination, source)
    if reason:
        raise SystemExit(f"{study_id}: fetched MAF is unusable -- {reason}")
    print(f"wrote   {destination}")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--study",
        default="nst_nfosi_ntap",
        choices=sorted(STUDIES),
        help="cBioPortal study id",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Destination MAF path (default data/raw/<study>_data_mutations.txt)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when a same-size cached copy exists",
    )
    args = parser.parse_args(argv)

    destination = args.output or Path("data/raw") / f"{args.study}_data_mutations.txt"
    try:
        fetch_maf(args.study, destination, force=args.force)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code} fetching {exc.url}: {exc.reason}") from exc
    return 0


if __name__ == "__main__":
    sys.exit(main())
