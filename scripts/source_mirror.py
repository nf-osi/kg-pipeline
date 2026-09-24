"""Mirror-first fetch for the pipeline's digest-pinned upstream sources.

## Why this exists

Every external input the graph is built from is pinned by a content digest — the
cBioPortal MAFs by their git-LFS `oid`, the Alliance orthology release by
`ORTHOLOGY_SHA256`, the GRCh38 reference by the digest in `build-image.yml`. A pin makes
a build *reproducible*, but it does nothing to make the bytes *available*: on
2026-09-23 `cBioPortal/datahub` exhausted its Git LFS budget and every one of the four
MAFs became un-downloadable, by anyone, with or without a token. The pins were still
perfectly valid and the variant layer still could not be built.

So the bytes are mirrored to a bucket we control, addressed by the digest that already
pins them:

    https://<mirror>/sha256/<digest>

## Why content addressing, and not a copy of the directory tree

The mirror is never trusted for *identity*, only for *availability*. The digest still
comes from upstream — `read_lfs_pointer` still reads cBioPortal's contents API,
`ORTHOLOGY_SHA256` is still the reviewed pin — and the downloaded bytes are hashed
against it whichever source served them. A mirror that served the wrong bytes, or a
stale copy, fails exactly as loudly as a corrupted upstream download. That is what makes
"try the mirror first" safe rather than a way to silently drift from upstream.

It also means the mirror needs no update when a pin moves: a new pin is a new digest, is
a new key. Nothing is ever overwritten, so nothing can rot.

## Disabling it

`KG_SOURCE_MIRROR=off` forces every fetch to upstream — for confirming that an outage
has lifted, or that a pin still matches what upstream serves.

Drift detection does not rely on that switch. `check_source_versions.py
--check-external` reads each module's URL attribute and streams it directly, never
through this module, so it cannot accidentally re-hash our own copy and report an
upstream change as "unchanged".
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

#: Public, read-only, in org-sagebase-sagebrain-prod (620117233256) -- the same account
#: as the Sage Brain deposit target, but a separate bucket: deposits are graph snapshots
#: written by a reviewed workflow, this is upstream source bytes written by hand.
#:
#: Public so that fetching needs no credentials: the data is open-access upstream, the
#: repo is public, and requiring AWS access to rebuild the graph would put contributors
#: behind a door upstream never had. The bucket policy grants anonymous `s3:GetObject`
#: on `sha256/*` and nothing else, so anything later written outside that prefix is
#: private by default rather than by remembering to make it so.
DEFAULT_MIRROR = "https://sagebrain-kg-sources.s3.us-east-1.amazonaws.com"

MIRROR_ENV = "KG_SOURCE_MIRROR"

_OFF = {"", "off", "none", "no", "0", "false"}

USER_AGENT = "nf-osi-kg-pipeline/source_mirror"


def mirror_base() -> str | None:
    """The mirror root, or None when it is switched off."""
    value = os.environ.get(MIRROR_ENV, DEFAULT_MIRROR)
    return None if value.strip().lower() in _OFF else value.rstrip("/")


def mirror_url(digest: str, algo: str = "sha256") -> str | None:
    """Where ``digest`` would live on the mirror, or None when it is switched off."""
    base = mirror_base()
    return f"{base}/{algo}/{digest}" if base else None


def sha256_file(path: Path) -> str:
    """Hash a file without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(
    url: str,
    destination: Path,
    expected_digest: str,
    expected_size: int | None = None,
) -> None:
    """Download to ``destination``, publishing the bytes only once they hash right.

    Written through a temporary file in the destination's own directory so a failed or
    interrupted download can never be mistaken for a cached copy on the next run.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=destination.name + ".", suffix=".part", delete=False
    ) as out:
        tmp = Path(out.name)
        try:
            written = 0
            digest = hashlib.sha256()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as resp:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
            if expected_size is not None and written != expected_size:
                raise SystemExit(
                    f"short read from {url}: got {written} bytes, pin declares {expected_size}"
                )
            if digest.hexdigest() != expected_digest:
                raise SystemExit(
                    f"SHA-256 mismatch from {url}: got {digest.hexdigest()}, "
                    f"pin declares {expected_digest}"
                )
            out.close()
            tmp.chmod(destination.stat().st_mode & 0o777 if destination.exists() else 0o644)
            tmp.replace(destination)
        finally:
            tmp.unlink(missing_ok=True)


def fetch_pinned(
    digest: str,
    destination: Path,
    upstream_url: Callable[[], str],
    *,
    size: int | None = None,
    label: str = "",
    log: Callable[[str], None] = print,
    download: Callable[[str, Path, str, int | None], None] = download_verified,
) -> Path:
    """Fetch ``digest`` to ``destination``, mirror first and upstream second.

    ``upstream_url`` is a *callable* rather than a string because resolving the upstream
    URL can itself be the expensive or failing step — for cBioPortal it means a round
    trip to the git-LFS batch endpoint, which is exactly what was down. A mirror hit
    must not pay for it, or trip over it.

    ``download`` is injectable for callers that already own their HTTP path. It must
    verify against the digest and publish atomically, exactly as `download_verified`
    does; mirror-first would otherwise become a way to skip verification.

    Both paths verify against ``digest``, so which one served the bytes is an
    availability detail and never a correctness one.
    """
    what = label or digest[:12]

    url = mirror_url(digest)
    if url:
        try:
            download(url, destination, digest, size)
            log(f"mirror  {what} -> {destination}")
            return destination
        except SystemExit:
            # A digest or size mismatch is never "try the next source" -- it means the
            # mirror is serving something it should not, and that needs to be seen.
            raise
        except (urllib.error.URLError, OSError) as exc:
            # A miss is ordinary: anything pinned since the last mirror push is simply
            # not there yet. Fall through to upstream and say so.
            log(f"mirror miss for {what} ({exc}); trying upstream")

    download(upstream_url(), destination, digest, size)
    log(f"upstream {what} -> {destination}")
    return destination
