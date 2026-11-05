# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-11-05

### Added
- `commerce download`: the nine Olist source files pinned to one commit and checked
  against SHA-256 digests.
- Schema contracts for every source table (types, nullability, keys, allowed codes,
  foreign keys).
- `commerce bronze`: a validated Parquet bronze layer with a manifest, registered as
  DuckDB views.
- `commerce replay`: orders replayed as an incremental stream of order events with a
  watermark and idempotent reruns.
- docs/DATA.md: source, licence, layers and table quirks.
- Project foundation: package layout, CI (ruff, mypy in strict mode, pytest on Python
  3.11 to 3.13, coverage gate, dependency audit), pinned dependencies, roadmap,
  contributor guide, security policy, issue and pull request templates.

[Unreleased]: https://github.com/mohammadazam7/ecommerce-data-ai-platform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mohammadazam7/ecommerce-data-ai-platform/releases/tag/v0.1.0
