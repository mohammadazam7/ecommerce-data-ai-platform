# ecommerce-data-ai-platform

[![CI](https://github.com/mohammadazam7/ecommerce-data-ai-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammadazam7/ecommerce-data-ai-platform/actions/workflows/ci.yml)

An end-to-end commerce data and machine learning platform on real marketplace data:
from raw order exports to tested data marts, customer analytics, production-style
models and controlled experiments.

> **Status:** in development. The project foundation is in place; see the
> [roadmap](docs/ROADMAP.md) for milestone dates. Results will be published here only
> once they have been measured.

## Overview

An online marketplace generates orders, payments, deliveries and reviews across
thousands of sellers. The questions that matter are cross-cutting: which customers are
worth retaining, how much a late delivery really costs in satisfaction, which orders are
likely to arrive late, how demand will move next month, and whether a change to the
checkout or delivery promise actually helped.

This project answers them on the public [Olist](https://github.com/olist/work-at-olist-data)
Brazilian marketplace data set: about 100,000 orders placed from 2016 to 2018, with
customers, sellers, products, payments, delivery dates and written reviews in
Portuguese. The data is real and anonymised, which keeps every result checkable.

## Architecture

```mermaid
flowchart LR
    O[Olist CSV exports] --> D[Download and<br/>schema contracts]
    D --> L[(Parquet lakehouse<br/>on DuckDB)]
    D --> E[Replayed order<br/>event stream]
    E --> L
    L --> T[dbt staging<br/>and marts]
    T --> A[Customer analytics:<br/>cohorts, RFM, CLV]
    T --> C[Causal study:<br/>late delivery vs reviews]
    T --> M[Models: late delivery,<br/>demand, sentiment]
    M --> R[MLflow tracking<br/>and registry]
    R --> S[FastAPI serving<br/>and drift monitoring]
    T --> X[Experimentation toolkit]
    T --> G[Commerce Globe<br/>3D web app]
```

| Layer | Responsibility |
|---|---|
| Ingestion | Download the exports, validate them against schema contracts, write a Parquet lakehouse, and replay orders as an event stream for incremental processing |
| Modelling | dbt marts for orders, customers, sellers, products, reviews and deliveries, with tests and contracts, orchestrated with data quality checks |
| Analytics | Cohort retention, RFM segmentation, customer lifetime value, and the effect of late deliveries on review scores |
| Machine learning | Late-delivery prediction, demand forecasting by category and review sentiment, each against a simple baseline, with model cards |
| Operations | Experiment tracking and a model registry, batch scoring, an HTTP service and drift monitoring |
| Experimentation | Power analysis, variance reduction (CUPED) and sequential testing on simulated experiments built from real baselines |

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
make install
make check

commerce download                 # nine Olist files, pinned and checksummed
commerce bronze                   # validate every table and write the bronze layer
commerce replay --batches 30      # replay the next 30 days of order events
```

`commerce bronze` refuses to write anything if a table breaks its contract. `commerce
replay` keeps a watermark in `data/lake/stream/order_events/`; run it again to continue,
or pass `--start` to rerun from an earlier time without duplicating events. See
[docs/DATA.md](docs/DATA.md) for the source, licence and table quirks.

## The marts

`dbt/` builds staging views over bronze and six marts in DuckDB:

- `marts.fct_orders`, one row per order: basket size, item and freight value, what was
  paid, delivery time and whether it arrived on a later calendar day than promised.
- `marts.dim_customers`, one row per person. Olist issues a new `customer_id` for every
  order, so a person is `customer_unique_id`; joining on `customer_id` would count every
  repeat buyer as a new customer.
- `marts.fct_order_items`, one row per item, with buyer, category in English and the
  seller's state joined in.
- `marts.fct_order_reviews`, one row per reviewed order. In the source an order can be
  reviewed more than once and one review can cover several orders, so the most recently
  answered review stands for the order and a count is kept.
- `marts.dim_products` and `marts.dim_sellers`, with what each sold. Items of canceled
  and unavailable orders are not sales. A seller's review score uses only orders where
  that seller was the only one, because a review belongs to an order, not to a seller.

```bash
cd dbt && dbt build --profiles-dir .
```

On the full data set (pinned commit; 13 models and 40 tests run in 3.2 seconds on 2 vCPUs
of an Intel Xeon at 2.80GHz): 99,441 orders from 96,096 people, of whom 2,997 ordered more
than once. 96,476 orders have a delivery date and 6,535 of those (6.8%) arrived after
the promised day. Payments match items plus freight to the cent for every order with
items except 450 (0.5%), and 775 orders have no items at all; a dbt test fails the build
if the mismatch passes 1%, which is what a join fanning out would look like.

The same run gives 112,650 items, 32,951 products (222 of them never sold, 610 without a
category) and 3,095 sellers. 98,673 orders have a review and 547 of those were reviewed
more than once. Reviewed orders that arrived on time average 4.29 stars and those that
arrived late 2.27. That is a description, not an effect: late orders differ from on-time
ones in other ways too (distance, category, season), and separating those is the causal
study in milestone 3.

## Data and licence

Code is released under the MIT licence. The Olist data set is published by Olist under
the MIT licence; it is downloaded by a script and not redistributed in this repository.
