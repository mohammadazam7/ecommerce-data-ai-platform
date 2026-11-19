"""Run the dbt project on a small bronze layer and check the order and customer marts.

The rows are chosen to hit the cases the marts handle on purpose: one person ordering
twice under two Olist customer_ids, a late delivery, a canceled order with no items, and
an order paid in two parts.
"""

import os
import shutil
import subprocess
from pathlib import Path

import duckdb
import pytest

from commerce_platform.lakehouse import build_bronze, register
from commerce_platform.sources import BY_TABLE

DBT_DIR = Path(__file__).resolve().parents[1] / "dbt"

ROWS = {
    "customers": "customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,"
    "customer_state\n"
    "c1,u1,01037,sao paulo,SP\n"
    "c2,u1,22041,rio de janeiro,RJ\n"
    "c3,u2,13023,campinas,SP\n",
    "sellers": "seller_id,seller_zip_code_prefix,seller_city,seller_state\n"
    "s1,13023,campinas,SP\ns2,01037,sao paulo,SP\n",
    "products": "product_id,product_category_name,product_name_lenght,product_description_lenght,"
    "product_photos_qty,product_weight_g,product_length_cm,product_height_cm,product_width_cm\n"
    "p1,perfumaria,40,287,1,225,16,10,14\np2,,,,,,,,\n",
    "orders": "order_id,customer_id,order_status,order_purchase_timestamp,order_approved_at,"
    "order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date\n"
    # on time: delivered before the promised day
    "o1,c1,delivered,2017-10-02 10:00:00,2017-10-02 11:00:00,2017-10-04 19:00:00,"
    "2017-10-10 22:00:00,2017-10-18 00:00:00\n"
    # same person, later address; delivered on the promised day, which is not late
    "o2,c2,delivered,2018-01-05 09:00:00,2018-01-05 10:00:00,2018-01-06 12:00:00,"
    "2018-01-20 15:00:00,2018-01-20 00:00:00\n"
    # late by one day
    "o3,c3,delivered,2018-03-01 08:00:00,2018-03-01 09:00:00,2018-03-02 10:00:00,"
    "2018-03-16 08:00:00,2018-03-15 00:00:00\n"
    # canceled before any item was picked
    "o4,c3,canceled,2018-04-01 08:00:00,,,,2018-04-20 00:00:00\n",
    "order_items": "order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,"
    "freight_value\n"
    "o1,1,p1,s1,2017-10-06 11:00:00,29.99,8.72\n"
    "o2,1,p1,s1,2018-01-09 10:00:00,29.99,10.00\n"
    "o2,2,p2,s2,2018-01-09 10:00:00,50.00,5.00\n"
    "o3,1,p2,s2,2018-03-05 09:00:00,100.00,20.00\n",
    "order_payments": "order_id,payment_sequential,payment_type,payment_installments,"
    "payment_value\n"
    "o1,1,credit_card,1,38.71\n"
    "o2,1,credit_card,3,74.99\n"
    "o2,2,voucher,1,20.00\n"
    "o3,1,boleto,1,120.00\n"
    "o4,1,credit_card,1,45.00\n",
    "order_reviews": "review_id,order_id,review_score,review_comment_title,"
    "review_comment_message,review_creation_date,review_answer_timestamp\n"
    "r1,o1,4,,,2017-10-11 00:00:00,2017-10-12 03:43:48\n",
    "geolocation": "geolocation_zip_code_prefix,geolocation_lat,geolocation_lng,"
    "geolocation_city,geolocation_state\n01037,-23.54,-46.63,sao paulo,SP\n",
    "category_translation": "product_category_name,product_category_name_english\n"
    "perfumaria,perfumery\n",
}


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> duckdb.DuckDBPyConnection:
    if shutil.which("dbt") is None:
        pytest.skip("dbt is not installed")
    root = tmp_path_factory.mktemp("commerce")
    landing = root / "landing"
    landing.mkdir()
    for table, text in ROWS.items():
        (landing / BY_TABLE[table].filename).write_text(text)
    build_bronze(landing, root / "lake")
    database = root / "commerce.duckdb"
    register(root / "lake", database)

    env = {**os.environ, "COMMERCE_DUCKDB": str(database)}
    target = root / "target"
    result = subprocess.run(
        [
            "dbt",
            "build",
            "--profiles-dir",
            ".",
            "--target-path",
            str(target),
            "--log-path",
            str(root / "logs"),
        ],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:]
    return duckdb.connect(str(database), read_only=True)


def _orders(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[object, ...]]:
    rows = con.sql(
        "select order_id, customer_unique_id, items, sellers, order_value, paid, "
        "main_payment_type, delivered_late from marts.fct_orders"
    ).fetchall()
    return {row[0]: row[1:] for row in rows}


def test_every_order_is_kept_once(warehouse: duckdb.DuckDBPyConnection) -> None:
    assert sorted(_orders(warehouse)) == ["o1", "o2", "o3", "o4"]


def test_baskets_and_payments_are_summed_without_fan_out(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    orders = _orders(warehouse)
    _, items, sellers, value, paid, main_type, _ = orders["o2"]
    assert (items, sellers) == (2, 2)
    assert value == pytest.approx(94.99)
    assert paid == pytest.approx(94.99)
    assert main_type == "credit_card"


def test_an_order_with_no_items_has_zero_value_and_no_delivery(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    _, items, _, value, paid, _, late = _orders(warehouse)["o4"]
    assert (items, value, late) == (0, 0, None)
    assert paid == pytest.approx(45.0)


def test_late_means_a_later_calendar_day_than_promised(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    orders = _orders(warehouse)
    assert orders["o1"][-1] is False
    assert orders["o2"][-1] is False
    assert orders["o3"][-1] is True


def test_customers_are_people_not_olist_customer_ids(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    rows = warehouse.sql(
        "select customer_unique_id, orders, round(lifetime_order_value, 2), state, city "
        "from marts.dim_customers order by 1"
    ).fetchall()
    assert rows == [
        ("u1", 2, 133.70, "RJ", "rio de janeiro"),
        ("u2", 2, 120.00, "SP", "campinas"),
    ]
