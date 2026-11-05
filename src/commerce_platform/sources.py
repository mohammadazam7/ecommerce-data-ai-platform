"""Download the Olist marketplace data at a pinned commit.

The data is the public Olist sample of about 100,000 orders placed on a Brazilian
marketplace between 2016 and 2018, published by Olist in
github.com/olist/work-at-olist-data under the MIT license. It is downloaded rather than
committed, and every file is pinned to one commit and checked against a SHA-256 digest,
so each run reads the same bytes and a changed upstream file fails loudly.
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

REPO = "olist/work-at-olist-data"
COMMIT = "d9e49802f3e92d09ee94ab9ccc5e457f207a8959"
ATTRIBUTION = "Olist marketplace data (https://github.com/olist/work-at-olist-data), MIT license"


@dataclass(frozen=True, slots=True)
class SourceFile:
    table: str
    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/datasets/{self.filename}"


FILES: tuple[SourceFile, ...] = (
    SourceFile(
        "customers",
        "olist_customers_dataset.csv",
        "c26c17f59f3027a6a0dbeb8f1fa373c38f3323ecc84f225a8f4820e5bb288df8",
    ),
    SourceFile(
        "geolocation",
        "olist_geolocation_dataset.csv",
        "b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6",
    ),
    SourceFile(
        "order_items",
        "olist_order_items_dataset.csv",
        "4f6abdbbc94036d0df4a76fa0520c072e31a40119d70f7f370fba1e2285d2bcb",
    ),
    SourceFile(
        "order_payments",
        "olist_order_payments_dataset.csv",
        "61674868ed7b872aac3dcd95bf774448a88f6426b183f21be55f75af021ffdec",
    ),
    SourceFile(
        "order_reviews",
        "olist_order_reviews_dataset.csv",
        "012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7",
    ),
    SourceFile(
        "orders",
        "olist_orders_dataset.csv",
        "8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf",
    ),
    SourceFile(
        "products",
        "olist_products_dataset.csv",
        "3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc",
    ),
    SourceFile(
        "sellers",
        "olist_sellers_dataset.csv",
        "31eb9bd50d684526a78f2389413ce61841e97692de7b828fe7d956b534586312",
    ),
    SourceFile(
        "category_translation",
        "product_category_name_translation.csv",
        "a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278",
    ),
)

BY_TABLE = {f.table: f for f in FILES}


class ChecksumError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(source: SourceFile, dest_dir: Path, *, timeout: float = 120.0) -> Path:
    """Fetch one file into ``dest_dir`` unless a verified copy is already there.

    The download is written to a temporary name and moved into place only after its
    digest matches, so an interrupted or altered download never looks complete.
    """
    dest = dest_dir / source.filename
    if dest.exists() and sha256(dest) == source.sha256:
        log.info("using cached %s", dest)
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    log.info("downloading %s", source.url)
    try:
        with urllib.request.urlopen(source.url, timeout=timeout) as resp, tmp.open("wb") as out:
            while block := resp.read(1 << 20):
                out.write(block)
        digest = sha256(tmp)
        if digest != source.sha256:
            raise ChecksumError(f"{source.filename}: expected {source.sha256}, got {digest}")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def fetch_all(dest_dir: Path, tables: Iterable[str] | None = None) -> dict[str, Path]:
    """Fetch every source file, or only ``tables``, and return table name to path."""
    wanted = list(tables) if tables is not None else [f.table for f in FILES]
    unknown = sorted(set(wanted) - BY_TABLE.keys())
    if unknown:
        raise KeyError(f"unknown tables: {', '.join(unknown)}")
    return {t: fetch(BY_TABLE[t], dest_dir) for t in wanted}
