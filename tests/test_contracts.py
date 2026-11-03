from pathlib import Path

import pyarrow as pa
import pytest

from commerce_platform.contracts import (
    CONTRACTS,
    Col,
    Contract,
    ContractError,
    ForeignKey,
    orphans,
    read,
    violations,
)
from commerce_platform.sources import FILES

PRODUCTS_CSV = (
    '"product_id","product_category_name","product_name_lenght","product_description_lenght",'
    '"product_photos_qty","product_weight_g","product_length_cm","product_height_cm",'
    '"product_width_cm"\n'
    '"p1",perfumaria,40,287,1,225,16,10,14\n'
    '"p2",,,,,700,30,10,20\n'
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_every_source_file_has_a_contract() -> None:
    assert {f.table for f in FILES} == set(CONTRACTS)
    for c in CONTRACTS.values():
        names = [col.name for col in c.columns]
        assert set(c.primary_key) <= set(names)
        for fk in c.foreign_keys:
            assert fk.column in names and fk.table in CONTRACTS


def test_read_renames_and_types_columns(tmp_path: Path) -> None:
    table = read(_write(tmp_path, "p.csv", PRODUCTS_CSV), CONTRACTS["products"])
    assert table.schema == CONTRACTS["products"].schema
    assert table.column("product_name_length").to_pylist() == [40, None]
    assert table.column("product_category_name").to_pylist() == ["perfumaria", None]


def test_read_keeps_leading_zeros_and_strips_bom(tmp_path: Path) -> None:
    text = "﻿seller_id,seller_zip_code_prefix,seller_city,seller_state\ns1,01037,sao paulo,SP\n"
    table = read(_write(tmp_path, "s.csv", text), CONTRACTS["sellers"])
    assert table.column("seller_zip_code_prefix").to_pylist() == ["01037"]


def test_header_drift_is_rejected(tmp_path: Path) -> None:
    renamed = PRODUCTS_CSV.replace("product_name_lenght", "product_name_length", 1)
    with pytest.raises(ContractError, match="missing columns"):
        read(_write(tmp_path, "p.csv", renamed), CONTRACTS["products"])
    extra = "seller_id,seller_zip_code_prefix,seller_city,seller_state,x\ns1,1,c,SP,1\n"
    with pytest.raises(ContractError, match="unexpected columns"):
        read(_write(tmp_path, "s.csv", extra), CONTRACTS["sellers"])


def test_bad_value_is_rejected(tmp_path: Path) -> None:
    text = "order_id,payment_sequential,payment_type,payment_installments,payment_value\n"
    text += "o1,1,boleto,one,10.0\n"
    with pytest.raises(ContractError, match="order_payments"):
        read(_write(tmp_path, "pay.csv", text), CONTRACTS["order_payments"])


TOY = Contract(
    "toy",
    (Col("id", pa.string()), Col("kind", pa.string(), allowed=frozenset({"a", "b"}))),
    ("id",),
    (ForeignKey("id", "parent", "id", max_orphan_share=0.0),),
)


def test_violations_report_nulls_codes_and_duplicate_keys() -> None:
    table = pa.table({"id": ["1", "1", None], "kind": ["a", "z", None]})
    found = violations(table, TOY)
    assert any("null values" in p for p in found)
    assert any("outside the allowed set" in p for p in found)
    assert any("duplicate keys" in p for p in found)
    assert violations(pa.table({"id": ["1", "2"], "kind": ["a", "b"]}), TOY) == []


def test_orphans() -> None:
    child = pa.table({"id": ["1", "2"], "kind": ["a", "a"]})
    assert orphans({"toy": child, "parent": pa.table({"id": ["1", "2"]})}, TOY) == []
    found = orphans({"toy": child, "parent": pa.table({"id": ["1"]})}, TOY)
    assert found == ["toy.id: 1 rows with no parent.id"]
    assert orphans({"toy": child}, TOY) == []
