import hashlib
import io
from pathlib import Path

import pytest

from commerce_platform import sources
from commerce_platform.sources import FILES, ChecksumError, SourceFile, fetch, fetch_all

BODY = b"order_id,price\na,1.0\n"
GOOD = SourceFile("orders", "orders.csv", hashlib.sha256(BODY).hexdigest())


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> _Response:
        calls.append(url)
        return _Response(BODY)

    monkeypatch.setattr(sources.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_every_file_is_pinned() -> None:
    assert len({f.table for f in FILES}) == len(FILES) == 9
    for f in FILES:
        assert sources.COMMIT in f.url and f.url.endswith(f.filename)
        assert len(f.sha256) == 64


def test_fetch_verifies_and_caches(tmp_path: Path, served: list[str]) -> None:
    path = fetch(GOOD, tmp_path)
    assert path.read_bytes() == BODY
    fetch(GOOD, tmp_path)
    assert len(served) == 1, "a verified copy is reused"


def test_checksum_mismatch_leaves_nothing_behind(tmp_path: Path, served: list[str]) -> None:
    bad = SourceFile("orders", "orders.csv", "0" * 64)
    with pytest.raises(ChecksumError):
        fetch(bad, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_fetch_all_rejects_unknown_tables(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="nope"):
        fetch_all(tmp_path, ["orders", "nope"])


def test_cli_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from commerce_platform import cli

    seen: list[list[str] | None] = []

    def fake_fetch_all(out: Path, tables: list[str] | None) -> dict[str, Path]:
        seen.append(tables)
        return {"orders": out / "orders.csv"}

    monkeypatch.setattr(cli, "fetch_all", fake_fetch_all)
    assert cli.main(["download", "--out", str(tmp_path), "--table", "orders"]) == 0
    assert seen == [["orders"]]
