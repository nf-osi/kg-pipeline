"""Cover the mirror-first fetch order and, more importantly, what it must never do.

The risk this module introduces is not "the mirror is down" -- that is the ordinary case
it exists to handle. The risk is that preferring our own copy quietly becomes a way to
skip verification, or to keep serving a stale object after a pin moves. The tests below
are mostly about that.

No network: every case injects a fake downloader, which is the same seam production
callers use (`fetch_cbioportal_maf` passes its own).
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import source_mirror  # noqa: E402

DIGEST = "a" * 64


@pytest.fixture(autouse=True)
def _default_mirror(monkeypatch):
    """Pin the mirror root so tests do not depend on the ambient environment."""
    monkeypatch.setenv(source_mirror.MIRROR_ENV, "https://mirror.example")


def recorder(fail_urls=(), published=True):
    """A stand-in downloader that records URLs and can fail selected ones."""
    seen = []

    def download(url, destination, digest, size):
        seen.append(url)
        if url in fail_urls:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if published:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(f"bytes from {url}")

    return download, seen


def test_mirror_is_tried_before_upstream(tmp_path):
    download, seen = recorder()
    upstream = lambda: pytest.fail("upstream must not be resolved when the mirror has it")

    source_mirror.fetch_pinned(
        DIGEST, tmp_path / "f", upstream, download=download, log=lambda _: None
    )

    assert seen == [f"https://mirror.example/sha256/{DIGEST}"]


def test_upstream_url_is_not_even_resolved_on_a_mirror_hit(tmp_path):
    """Resolving upstream is the expensive, failing step -- a hit must not pay for it."""
    calls = []

    def upstream():
        calls.append(1)
        return "https://upstream.example/x"

    download, _ = recorder()
    source_mirror.fetch_pinned(
        DIGEST, tmp_path / "f", upstream, download=download, log=lambda _: None
    )
    assert calls == []


def test_mirror_miss_falls_through_to_upstream(tmp_path):
    mirror = f"https://mirror.example/sha256/{DIGEST}"
    download, seen = recorder(fail_urls={mirror})

    source_mirror.fetch_pinned(
        DIGEST,
        tmp_path / "f",
        lambda: "https://upstream.example/x",
        download=download,
        log=lambda _: None,
    )

    assert seen == [mirror, "https://upstream.example/x"]


def test_digest_mismatch_from_the_mirror_is_fatal_not_a_miss(tmp_path):
    """A wrong object must stop the build, not silently reroute to upstream.

    Falling through would hide that the mirror is serving something it should not, which
    is the one failure content addressing exists to make impossible to ignore.
    """
    def download(url, destination, digest, size):
        raise SystemExit("SHA-256 mismatch")

    with pytest.raises(SystemExit, match="SHA-256 mismatch"):
        source_mirror.fetch_pinned(
            DIGEST,
            tmp_path / "f",
            lambda: pytest.fail("must not fall through after a digest mismatch"),
            download=download,
            log=lambda _: None,
        )


@pytest.mark.parametrize("value", ["off", "none", "0", "false", ""])
def test_mirror_can_be_switched_off(tmp_path, monkeypatch, value):
    monkeypatch.setenv(source_mirror.MIRROR_ENV, value)
    download, seen = recorder()

    source_mirror.fetch_pinned(
        DIGEST,
        tmp_path / "f",
        lambda: "https://upstream.example/x",
        download=download,
        log=lambda _: None,
    )

    assert seen == ["https://upstream.example/x"]
    assert source_mirror.mirror_url(DIGEST) is None


def test_a_moved_pin_asks_for_a_different_key(tmp_path):
    """Content addressing is what makes a stale mirror object unreachable rather than wrong."""
    assert source_mirror.mirror_url("b" * 64) != source_mirror.mirror_url(DIGEST)
    assert source_mirror.mirror_url(DIGEST).endswith(f"/sha256/{DIGEST}")


def test_download_verified_publishes_nothing_on_mismatch(tmp_path, monkeypatch):
    """The real downloader must not leave a partial file that later looks like a cache."""
    import io

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        source_mirror.urllib.request, "urlopen",
        lambda *a, **k: FakeResponse(b"wrong bytes"),
    )
    destination = tmp_path / "f"

    with pytest.raises(SystemExit, match="SHA-256 mismatch"):
        source_mirror.download_verified("https://mirror.example/x", destination, DIGEST)

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []
