"""Schema contracts for the Olist source tables.

A contract states what downstream code may assume about a table: its columns and their
types, which columns may be null, the primary key, the allowed values of coded
columns and the foreign keys into other tables. Source files are read through their
contract, so a renamed or retyped upstream column fails at the boundary instead of
surfacing later as a wrong number.

The facts encoded here were checked against the pinned source files:

* ``order_reviews.review_id`` is not unique on its own (a review can cover several
  orders), so the key is ``(review_id, order_id)``.
* The products file misspells ``length`` as ``lenght`` in two column names; the
  contract renames them.
* Delivery timestamps are null for orders that never shipped or were not delivered,
  and about 2% of products have no category.
* Zip code prefixes are text: they have leading zeros.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

TIMESTAMP = pa.timestamp("s")


@dataclass(frozen=True, slots=True)
class Col:
    name: str
    type: pa.DataType
    nullable: bool = False
    source: str | None = None  # name in the source file when it differs
    allowed: frozenset[str] | None = None

    @property
    def source_name(self) -> str:
        return self.source or self.name


@dataclass(frozen=True, slots=True)
class ForeignKey:
    column: str
    table: str
    to_column: str
    # Share of rows allowed to point at nothing; the source has a few known orphans.
    max_orphan_share: float = 0.0


@dataclass(frozen=True, slots=True)
class Contract:
    table: str
    columns: tuple[Col, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...] = field(default=())

    @property
    def schema(self) -> pa.Schema:
        return pa.schema([pa.field(c.name, c.type, nullable=c.nullable) for c in self.columns])


def _codes(*values: str) -> frozenset[str]:
    return frozenset(values)


STR, FLOAT, INT, TS = pa.string(), pa.float64(), pa.int32(), TIMESTAMP

CONTRACTS: Mapping[str, Contract] = {
    c.table: c
    for c in (
        Contract(
            "orders",
            (
                Col("order_id", STR),
                Col("customer_id", STR),
                Col(
                    "order_status",
                    STR,
                    allowed=_codes(
                        "created",
                        "approved",
                        "invoiced",
                        "processing",
                        "shipped",
                        "delivered",
                        "canceled",
                        "unavailable",
                    ),
                ),
                Col("order_purchase_timestamp", TS),
                Col("order_approved_at", TS, nullable=True),
                Col("order_delivered_carrier_date", TS, nullable=True),
                Col("order_delivered_customer_date", TS, nullable=True),
                Col("order_estimated_delivery_date", TS),
            ),
            ("order_id",),
            (ForeignKey("customer_id", "customers", "customer_id"),),
        ),
        Contract(
            "order_items",
            (
                Col("order_id", STR),
                Col("order_item_id", INT),
                Col("product_id", STR),
                Col("seller_id", STR),
                Col("shipping_limit_date", TS),
                Col("price", FLOAT),
                Col("freight_value", FLOAT),
            ),
            ("order_id", "order_item_id"),
            (
                ForeignKey("order_id", "orders", "order_id"),
                ForeignKey("product_id", "products", "product_id"),
                ForeignKey("seller_id", "sellers", "seller_id"),
            ),
        ),
        Contract(
            "order_payments",
            (
                Col("order_id", STR),
                Col("payment_sequential", INT),
                Col(
                    "payment_type",
                    STR,
                    allowed=_codes("credit_card", "boleto", "voucher", "debit_card", "not_defined"),
                ),
                Col("payment_installments", INT),
                Col("payment_value", FLOAT),
            ),
            ("order_id", "payment_sequential"),
            (ForeignKey("order_id", "orders", "order_id"),),
        ),
        Contract(
            "order_reviews",
            (
                Col("review_id", STR),
                Col("order_id", STR),
                Col("review_score", INT),
                Col("review_comment_title", STR, nullable=True),
                Col("review_comment_message", STR, nullable=True),
                Col("review_creation_date", TS),
                Col("review_answer_timestamp", TS),
            ),
            ("review_id", "order_id"),
            (ForeignKey("order_id", "orders", "order_id"),),
        ),
        Contract(
            "customers",
            (
                Col("customer_id", STR),
                Col("customer_unique_id", STR),
                Col("customer_zip_code_prefix", STR),
                Col("customer_city", STR),
                Col("customer_state", STR),
            ),
            ("customer_id",),
        ),
        Contract(
            "sellers",
            (
                Col("seller_id", STR),
                Col("seller_zip_code_prefix", STR),
                Col("seller_city", STR),
                Col("seller_state", STR),
            ),
            ("seller_id",),
        ),
        Contract(
            "products",
            (
                Col("product_id", STR),
                Col("product_category_name", STR, nullable=True),
                Col("product_name_length", INT, nullable=True, source="product_name_lenght"),
                Col(
                    "product_description_length",
                    INT,
                    nullable=True,
                    source="product_description_lenght",
                ),
                Col("product_photos_qty", INT, nullable=True),
                Col("product_weight_g", FLOAT, nullable=True),
                Col("product_length_cm", FLOAT, nullable=True),
                Col("product_height_cm", FLOAT, nullable=True),
                Col("product_width_cm", FLOAT, nullable=True),
            ),
            ("product_id",),
        ),
        Contract(
            "geolocation",
            (
                Col("geolocation_zip_code_prefix", STR),
                Col("geolocation_lat", FLOAT),
                Col("geolocation_lng", FLOAT),
                Col("geolocation_city", STR),
                Col("geolocation_state", STR),
            ),
            (),  # many coordinates per prefix; aggregated downstream
        ),
        Contract(
            "category_translation",
            (Col("product_category_name", STR), Col("product_category_name_english", STR)),
            ("product_category_name",),
        ),
    )
}


class ContractError(ValueError):
    pass


def read(path: Path, contract: Contract) -> pa.Table:
    """Read a source CSV into the contract's schema, renaming source columns.

    Raises :class:`ContractError` if the header is missing a contracted column or has
    one the contract does not know about, or a value cannot be cast to its type.
    """
    header = _header(path)
    expected = [c.source_name for c in contract.columns]
    if missing := sorted(set(expected) - set(header)):
        raise ContractError(f"{contract.table}: missing columns {missing}")
    if extra := sorted(set(header) - set(expected)):
        raise ContractError(f"{contract.table}: unexpected columns {extra}")
    opts = pacsv.ConvertOptions(
        column_types={c.source_name: c.type for c in contract.columns},
        strings_can_be_null=True,
        timestamp_parsers=["%Y-%m-%d %H:%M:%S"],
    )
    try:
        table = pacsv.read_csv(
            path, read_options=pacsv.ReadOptions(encoding="utf-8-sig"), convert_options=opts
        )
    except pa.ArrowInvalid as exc:
        raise ContractError(f"{contract.table}: {exc}") from exc
    table = table.select(expected).rename_columns([c.name for c in contract.columns])
    return table.cast(contract.schema)


def _header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        first = f.readline()
    names: list[str] = pacsv.read_csv(pa.py_buffer(first.encode())).schema.names
    return names


def violations(table: pa.Table, contract: Contract) -> list[str]:
    """Row-level rules the table breaks: nulls, duplicate keys and unknown codes."""
    problems: list[str] = []
    for col in contract.columns:
        values = table.column(col.name)
        if not col.nullable and (n := values.null_count):
            problems.append(f"{contract.table}.{col.name}: {n} null values")
        if col.allowed is not None:
            ok = pc.is_in(values, value_set=pa.array(sorted(col.allowed)))
            if n := pc.sum(pc.invert(pc.fill_null(ok, True))).as_py() or 0:
                problems.append(f"{contract.table}.{col.name}: {n} values outside the allowed set")
    if contract.primary_key:
        keys = table.group_by(list(contract.primary_key)).aggregate([([], "count_all")])
        dupes = pc.sum(pc.greater(keys.column("count_all"), 1)).as_py() or 0
        if dupes:
            key = ", ".join(contract.primary_key)
            problems.append(f"{contract.table}: {dupes} duplicate keys on ({key})")
    return problems


def orphans(tables: Mapping[str, pa.Table], contract: Contract) -> list[str]:
    """Foreign keys whose share of unmatched rows exceeds what the contract allows."""
    problems: list[str] = []
    child = tables[contract.table]
    for fk in contract.foreign_keys:
        if fk.table not in tables:
            continue
        parent = tables[fk.table].column(fk.to_column)
        found = pc.is_in(child.column(fk.column), value_set=pc.unique(parent))
        missing = pc.sum(pc.invert(found)).as_py() or 0
        if child.num_rows and missing / child.num_rows > fk.max_orphan_share:
            problems.append(
                f"{contract.table}.{fk.column}: {missing} rows with no {fk.table}.{fk.to_column}"
            )
    return problems
