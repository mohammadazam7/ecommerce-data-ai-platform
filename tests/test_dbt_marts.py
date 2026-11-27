"""Run the dbt project on a small bronze layer and check the marts.

The rows are chosen to hit the cases the marts handle on purpose: one person ordering
twice under two Olist customer_ids, a late delivery, a canceled order with no items, a
canceled order with an item, an order paid in two parts, an order reviewed twice, one
review covering two orders, a product with no category, a category with no translation,
and a seller and a product that never sold.
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
    "c3,u2,13023,campinas,SP\n"
    "c4,u3,80010,curitiba,PR\n",
    "sellers": "seller_id,seller_zip_code_prefix,seller_city,seller_state\n"
    "s1,13023,campinas,SP\ns2,01037,sao paulo,SP\ns3,80010,curitiba,PR\n",
    "products": "product_id,product_category_name,product_name_lenght,product_description_lenght,"
    "product_photos_qty,product_weight_g,product_length_cm,product_height_cm,product_width_cm\n"
    "p1,perfumaria,40,287,1,225,16,10,14\np2,,,,,,,,\np3,pc_gamer,30,100,2,9000,50,40,30\n",
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
    "o4,c3,canceled,2018-04-01 08:00:00,,,,2018-04-20 00:00:00\n"
    # canceled after an item was picked: the item exists but is not a sale
    "o5,c4,canceled,2018-05-01 08:00:00,2018-05-01 09:00:00,,,2018-05-20 00:00:00\n",
    "order_items": "order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,"
    "freight_value\n"
    "o1,1,p1,s1,2017-10-06 11:00:00,29.99,8.72\n"
    "o2,1,p1,s1,2018-01-09 10:00:00,29.99,10.00\n"
    "o2,2,p2,s2,2018-01-09 10:00:00,50.00,5.00\n"
    "o3,1,p2,s2,2018-03-05 09:00:00,100.00,20.00\n"
    "o5,1,p1,s2,2018-05-05 09:00:00,10.00,2.00\n",
    "order_payments": "order_id,payment_sequential,payment_type,payment_installments,"
    "payment_value\n"
    "o1,1,credit_card,1,38.71\n"
    "o2,1,credit_card,3,74.99\n"
    "o2,2,voucher,1,20.00\n"
    "o3,1,boleto,1,120.00\n"
    "o4,1,credit_card,1,45.00\n"
    "o5,1,credit_card,1,12.00\n",
    "order_reviews": "review_id,order_id,review_score,review_comment_title,"
    "review_comment_message,review_creation_date,review_answer_timestamp\n"
    "r1,o1,4,,,2017-10-11 00:00:00,2017-10-12 03:43:48\n"
    # the same order reviewed again later with a different score and a comment
    "r2,o1,2,,stopped working,2017-10-19 00:00:00,2017-10-20 10:00:00\n"
    # one review covering two orders
    "r3,o2,5,,,2018-01-21 00:00:00,2018-01-22 09:00:00\n"
    "r3,o3,1,,   ,2018-03-17 00:00:00,2018-03-18 09:00:00\n",
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
    assert sorted(_orders(warehouse)) == ["o1", "o2", "o3", "o4", "o5"]


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
        ("u3", 1, 12.00, "PR", "curitiba"),
    ]


def test_items_carry_buyer_category_and_seller_state(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    rows = warehouse.sql(
        "select order_id, order_item_id, customer_unique_id, category_english, seller_state "
        "from marts.fct_order_items order by 1, 2"
    ).fetchall()
    assert rows == [
        ("o1", 1, "u1", "perfumery", "SP"),
        ("o2", 1, "u1", "perfumery", "SP"),
        ("o2", 2, "u1", None, "SP"),
        ("o3", 1, "u2", None, "SP"),
        ("o5", 1, "u3", "perfumery", "SP"),
    ]


def test_an_order_reviewed_twice_keeps_its_latest_review(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    rows = warehouse.sql(
        "select order_id, review_id, score, has_comment, reviews, delivered_late, "
        "days_after_promise from marts.fct_order_reviews order by 1"
    ).fetchall()
    assert rows == [
        ("o1", "r2", 2, True, 2, False, -8),
        # one review id on two orders stays two rows, one per order
        ("o2", "r3", 5, False, 1, False, 0),
        ("o3", "r3", 1, False, 1, True, 1),  # a comment of only spaces is no comment
    ]


def test_products_keep_a_name_without_translation_and_count_only_real_sales(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    rows = warehouse.sql(
        "select product_id, category_english, volume_cm3, items_sold, orders, revenue "
        "from marts.dim_products order by 1"
    ).fetchall()
    assert rows == [
        ("p1", "perfumery", 2240.0, 2, 2, pytest.approx(59.98)),  # the canceled o5 is not a sale
        ("p2", None, None, 2, 2, pytest.approx(150.0)),
        ("p3", "pc_gamer", 60000.0, 0, 0, 0),
    ]


def test_sellers_get_lateness_from_all_orders_and_reviews_from_their_own(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    rows = warehouse.sql(
        "select seller_id, orders, items, revenue, delivered_orders, late_share, "
        "reviewed_orders, review_score from marts.dim_sellers order by 1"
    ).fetchall()
    assert rows == [
        # o1 and o2 delivered on time; only o1 was theirs alone, and its latest score is 2
        ("s1", 2, 2, pytest.approx(59.98), 2, 0.0, 1, 2.0),
        # o2 on time, o3 late; o3 was theirs alone; canceled o5 counts for nothing
        ("s2", 2, 2, pytest.approx(150.0), 2, 0.5, 1, 1.0),
        ("s3", 0, 0, 0, 0, None, 0, None),
    ]
