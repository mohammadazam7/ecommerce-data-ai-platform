# Data

## Source

The Olist marketplace sample: about 100,000 orders placed on a Brazilian marketplace
between 2016 and 2018, with their items, payments, reviews, customers, sellers, products
and zip code geolocation. Olist publishes it in
[olist/work-at-olist-data](https://github.com/olist/work-at-olist-data) under the MIT
license. The same data is also distributed on Kaggle under CC BY-NC-SA 4.0; this project
is non-commercial and attributes Olist in every output.

Nothing from the source is committed. `commerce download` fetches the nine files from
commit `d9e49802f3e92d09ee94ab9ccc5e457f207a8959` and checks each against a SHA-256 in
`src/commerce_platform/sources.py`.

## Layers

| Layer | Where | What |
| --- | --- | --- |
| Landing | `data/landing/` | The source CSV files exactly as downloaded, checksummed |
| Bronze | `data/lake/bronze/<table>/<table>.parquet` | Each table read through its contract: typed, renamed, validated |
| Warehouse | `data/warehouse.duckdb` | `bronze.<table>` views over the Parquet files |

`commerce bronze` writes bronze only when every table passes its contract, and records
in `data/lake/_manifest.json` the row count and checksum of each Parquet file and of the
source file it came from.

## Tables

| Table | Rows | Key | Notes |
| --- | ---: | --- | --- |
| orders | 99,441 | order_id | Delivery timestamps are null when an order never shipped or was not delivered |
| order_items | 112,650 | (order_id, order_item_id) | One row per item; price and freight in BRL |
| order_payments | 103,886 | (order_id, payment_sequential) | An order can be paid in several parts |
| order_reviews | 99,224 | (review_id, order_id) | review_id alone repeats: one review can cover several orders |
| customers | 99,441 | customer_id | customer_id is per order; customer_unique_id identifies the person |
| sellers | 3,095 | seller_id | |
| products | 32,951 | product_id | 610 products have no category; the source misspells two column names, renamed here |
| geolocation | 1,000,163 | none | Many coordinates per zip code prefix; aggregated downstream |
| category_translation | 71 | product_category_name | Portuguese to English; two categories in products have no translation |

Zip code prefixes are kept as text so leading zeros survive.

## Known limits

- The sample is a subset of Olist's orders, anonymised by Olist; company names in
  reviews were replaced with the names of Game of Thrones houses by the publisher.
- `customer_id` changes with every order, so repeat-customer analysis must use
  `customer_unique_id`.
- Timestamps have no time zone; they are treated as Brasilia time, which was UTC-3 and
  UTC-2 during the daylight saving periods Brazil still observed from 2016 to 2018.
