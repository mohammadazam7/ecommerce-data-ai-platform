# Security policy

## Reporting a problem

Please report security issues privately through GitHub's
[security advisories](https://github.com/mohammadazam7/ecommerce-data-ai-platform/security/advisories/new)
rather than in a public issue. Expect an acknowledgement within a few days.

## Data and credentials

- The Olist data is a public, anonymised marketplace sample. It is downloaded by a
  script and never committed.
- Credentials (for example a BigQuery service account key) are read from the
  environment and are never committed. `.gitignore` excludes common key file names.
- Customer and seller identifiers are hashed in the source data; models never use them
  as features.
