# Roadmap

Each milestone lands on its own branch with tests and is merged when complete. Checked
items are done.

- [x] **M1: Foundation and data** (Nov 2 to Nov 5). Package layout, CI, a download
      script pinned to a commit of the Olist repository, schema contracts for each
      table, a Parquet lakehouse on DuckDB, and an order event stream replayed in time
      order for incremental loads.
- [ ] **M2: Data models and orchestration** (Nov 6 to Nov 10). dbt marts for orders,
      customers, sellers, products, reviews and deliveries in a star schema, with tests
      and contracts, orchestrated as an asset graph with data quality checks.
- [ ] **M3: Customer analytics and causal study** (Nov 11 to Nov 22). Cohort
      retention, RFM segmentation, customer lifetime value, and an estimate of how late
      deliveries change review scores with the assumptions stated.
- [ ] **M4: Models and serving** (Nov 23 to Dec 5). Late-delivery prediction, demand
      forecasting with backtests and review sentiment, each against a baseline;
      experiment tracking, a model registry, batch scoring and an HTTP service.
- [ ] **M5: Experimentation, monitoring and Commerce Globe** (Dec 6 to Dec 19). Power
      analysis, CUPED and sequential testing; drift monitoring with alerts; an
      interactive 3D web app.
- [ ] **M6: v1.0** (Dec 20 to Dec 27). Executive readout, design document, decision
      records and release.
