"""Bronze layer of the lakehouse: contracted source tables as Parquet, queryable in DuckDB.

``build_bronze`` reads each landed source file through its contract
(:mod:`commerce_platform.contracts`), stops if any table breaks its row-level rules or
foreign keys, and writes one Parquet file per table. Files are written to a temporary
name and renamed into place, and ``_manifest.json`` records for every table its row
count, the SHA-256 of the Parquet file and of the source file it came from, so a
downstream run can tell exactly which bytes it read.

``register`` creates a DuckDB database with a ``bronze`` schema of views over those files.
The views hold no data, so rebuilding bronze never requires rebuilding the database.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from commerce_platform.contracts import CONTRACTS, orphans, read, violations
from commerce_platform.sources import ATTRIBUTION, BY_TABLE, COMMIT, sha256

log = logging.getLogger(__name__)

MANIFEST = "_manifest.json"


class QualityError(RuntimeError):
    """A source table broke its contract; nothing was written."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _bronze_path(lake: Path, table: str) -> Path:
    return lake / "bronze" / table / f"{table}.parquet"


def build_bronze(landing: Path, lake: Path) -> dict[str, Any]:
    """Validate every landed source table and write it to ``lake/bronze``.

    All tables are read and checked before any file is written, so a failed check
    leaves the previous bronze layer untouched.
    """
    tables: dict[str, pa.Table] = {}
    problems: list[str] = []
    for name, contract in CONTRACTS.items():
        tables[name] = read(landing / BY_TABLE[name].filename, contract)
        problems += violations(tables[name], contract)
    for contract in CONTRACTS.values():
        problems += orphans(tables, contract)
    if problems:
        raise QualityError(problems)

    entries: dict[str, Any] = {}
    for name, table in tables.items():
        target = _bronze_path(lake, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp, compression="zstd")
        os.replace(tmp, target)
        entries[name] = {
            "path": str(target.relative_to(lake)),
            "rows": table.num_rows,
            "sha256": sha256(target),
            "source_sha256": BY_TABLE[name].sha256,
        }
        log.info("bronze %s rows=%d", name, table.num_rows)
    manifest = {"source_commit": COMMIT, "attribution": ATTRIBUTION, "tables": entries}
    (lake / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def register(lake: Path, database: Path) -> list[str]:
    """Create or refresh ``bronze.<table>`` views in a DuckDB file; returns their names."""
    import duckdb

    manifest = json.loads((lake / MANIFEST).read_text())
    database.parent.mkdir(parents=True, exist_ok=True)
    names = []
    with duckdb.connect(str(database)) as con:
        con.execute("create schema if not exists bronze")
        for name, meta in sorted(manifest["tables"].items()):
            path = (lake / meta["path"]).resolve().as_posix().replace("'", "''")
            con.execute(
                f"create or replace view bronze.\"{name}\" as select * from read_parquet('{path}')"
            )
            names.append(f"bronze.{name}")
    return names
