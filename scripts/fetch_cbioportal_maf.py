"""Fetch a cBioPortal study's MAF (`data_mutations.txt`) for the variant layer.

Part of the variant layer PoC (nf-osi/kg-pipeline#95). See `docs/variant-layer.md`.

## Why this is not just a `curl`

cBioPortal study files live in git-LFS-backed datahub repos, so the path that looks like
a file (`public/<study>/data_mutations.txt`) actually serves a ~130-byte LFS *pointer*.
Getting the bytes means: read the pointer, extract `oid`/`size`, ask the repo's LFS
batch endpoint for a signed URL, then download that. `git clone` would drag the whole
multi-GB datahub along, so the batch API is used directly.

## Which source, and why not the obvious ones

| Source | Status |
|---|---|
| `nf-osi/datahub` fork | **Used.** Full 113-column MAF including `Consequence` (SO terms), `HGVSc`/`HGVSp`, `HGNC_ID`, gnomAD AF. Pinned at 2025-02, so stale relative to cBioPortal's own import, but complete. |
| `cBioPortal/datahub` upstream | Has the study, but its LFS objects answer `404 Object does not exist on the server`. Unusable. |
| cBioPortal REST API | Current and needs no LFS, but drops `Consequence`, `HGVSc`, `HGVSp`, `HGNC_ID` and gnomAD AF -- i.e. everything the SSSOM consequence mapping and protein-change search rely on. Kept as a documented fallback, not implemented. |

Adding a study is a `STUDIES` entry. Note `nfib_ctf_biobank_2025` is deliberately absent:
its MAF is only in the upstream datahub (404s), and its sample ids cannot be mapped to
portal specimens at all, so it cannot join to the graph at specimen level.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GITHUB_API = "https://api.github.com"
USER_AGENT = "nf-osi-kg-pipeline/fetch_cbioportal_maf"


@dataclass(frozen=True)
class StudySource:
    """Where a study's MAF lives."""

    study_id: str
    repo: str
    path: str
    ref: str = "master"
    #: Assembly the MAF declares, asserted against the seqmap by `vrsify maf`.
    assembly: str = "GRCh38"


STUDIES: dict[str, StudySource] = {
    "nst_nfosi_ntap": StudySource(
        study_id="nst_nfosi_ntap",
        repo="nf-osi/datahub",
        path="public/nst_nfosi_ntap/data_mutations.txt",
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


def download(url: str, destination: Path, expected_size: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    written = 0
    with _request(url) as resp, open(tmp, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            written += len(chunk)
    if written != expected_size:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"short read: got {written} bytes, pointer declared {expected_size}"
        )
    tmp.replace(destination)


def fetch_maf(study_id: str, destination: Path, force: bool = False) -> Path:
    """Download ``study_id``'s MAF to ``destination``, reusing a cached copy.

    The cache check is by declared LFS size: a stale local file from a different
    revision has a different size, so it gets replaced rather than silently reused.
    """
    source = STUDIES.get(study_id)
    if source is None:
        raise SystemExit(
            f"unknown study {study_id!r}; known: {', '.join(sorted(STUDIES))}. "
            "Add a STUDIES entry to fetch a new one."
        )

    oid, size = read_lfs_pointer(source)
    if destination.exists() and not force:
        if destination.stat().st_size == size:
            print(f"cached  {destination} ({size} bytes, oid {oid[:12]}...)")
            return destination
        print(
            f"replacing {destination}: {destination.stat().st_size} bytes on disk, "
            f"{size} declared upstream"
        )

    url = resolve_lfs_download(source, oid, size)
    print(f"fetching {source.repo}/{source.path} -> {destination} ({size} bytes)")
    download(url, destination, size)
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
