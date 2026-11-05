import json
from pathlib import Path

import duckdb
import pytest

from commerce_platform import lakehouse
from commerce_platform.cli import main
from commerce_platform.contracts import CONTRACTS
from commerce_platform.lakehouse import QualityError, build_bronze, register
from commerce_platform.sources import BY_TABLE

ROWS = {
    "customers": "customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,"
    "customer_state\nc1,u1,01037,sao paulo,SP\n",
    "sellers": "seller_id,seller_zip_code_prefix,seller_city,seller_state\ns1,13023,campinas,SP\n",
    "products": "product_id,product_category_name,product_name_lenght,product_description_lenght,"
    "product_photos_qty,product_weight_g,product_length_cm,product_height_cm,product_width_cm\n"
    "p1,perfumaria,40,287,1,225,16,10,14\n",
    "orders": "order_id,customer_id,order_status,order_purchase_timestamp,order_approved_at,"
    "order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date\n"
    "o1,c1,delivered,2017-10-02 10:56:33,2017-10-02 11:07:15,2017-10-04 19:55:00,"
    "2017-10-10 21:25:13,2017-10-18 00:00:00\n",
    "order_items": "order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,"
    "freight_value\no1,1,p1,s1,2017-10-06 11:07:15,29.99,8.72\n",
    "order_payments": "order_id,payment_sequential,payment_type,payment_installments,"
    "payment_value\no1,1,credit_card,1,38.71\n",
    "order_reviews": "review_id,order_id,review_score,review_comment_title,"
    "review_comment_message,review_creation_date,review_answer_timestamp\n"
    "r1,o1,4,,,2017-10-11 00:00:00,2017-10-12 03:43:48\n",
    "geolocation": "geolocation_zip_code_prefix,geolocation_lat,geolocation_lng,"
    "geolocation_city,geolocation_state\n01037,-23.54,-46.63,sao paulo,SP\n",
    "category_translation": "product_category_name,product_category_name_english\n"
    "perfumaria,perfumery\n",
}


@pytest.fixture
def landing(tmp_path: Path) -> Path:
    root = tmp_path / "landing"
    root.mkdir()
    assert set(ROWS) == set(CONTRACTS)
    for table, text in ROWS.items():
        (root / BY_TABLE[table].filename).write_text(text, encoding="utf-8")
    return root


def test_bronze_round_trip(landing: Path, tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    manifest = build_bronze(landing, lake)
    assert manifest["tables"]["orders"]["rows"] == 1
    views = register(lake, tmp_path / "w.duckdb")
    assert "bronze.order_items" in views
    with duckdb.connect(str(tmp_path / "w.duckdb"), read_only=True) as con:
        total = con.execute(
            "select sum(i.price + i.freight_value) from bronze.order_items i "
            "join bronze.orders o using (order_id) where o.order_status = 'delivered'"
        ).fetchall()[0][0]
        zip_code = con.execute("select customer_zip_code_prefix from bronze.customers").fetchall()
    assert total == pytest.approx(38.71)
    assert zip_code == [("01037",)]


def test_quality_failure_writes_nothing(landing: Path, tmp_path: Path) -> None:
    orders = landing / BY_TABLE["orders"].filename
    orders.write_text(orders.read_text().replace(",c1,", ",c_missing,"), encoding="utf-8")
    lake = tmp_path / "lake"
    with pytest.raises(QualityError) as info:
        build_bronze(landing, lake)
    assert any("orders.customer_id" in p for p in info.value.problems)
    assert not lake.exists()


def test_cli_bronze(landing: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["bronze", "--landing", str(landing), "--lake", str(tmp_path / "lake")]
    args += ["--database", str(tmp_path / "w.duckdb")]
    assert main(args) == 0
    manifest = json.loads((tmp_path / "lake" / lakehouse.MANIFEST).read_text())
    assert set(manifest["tables"]) == set(CONTRACTS)
    (landing / BY_TABLE["sellers"].filename).write_text(
        "seller_id,seller_zip_code_prefix,seller_city,seller_state\ns1,1,c,SP\ns1,2,d,RJ\n"
    )
    assert main(args) == 1
    assert "duplicate keys" in capsys.readouterr().out


def test_cli_replay(landing: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lake = tmp_path / "lake"
    main(
        [
            "bronze",
            "--landing",
            str(landing),
            "--lake",
            str(lake),
            "--database",
            str(tmp_path / "w.duckdb"),
        ]
    )
    assert main(["replay", "--lake", str(lake), "--batches", "3"]) == 0
    out = capsys.readouterr().out
    assert "watermark" in out
    assert main(["replay", "--lake", str(lake), "--start", "2017-10-01T00:00:00"]) == 0
