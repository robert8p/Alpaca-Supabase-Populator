# Release notes

## 1.0.1 — Render Python runtime fix

- Pins `PYTHON_VERSION=3.12.7` explicitly for both Render services.
- Makes the build log print the selected Python version.
- Requires prebuilt wheels during dependency installation, preventing unsupported source builds in Render.
- Adds deployment troubleshooting for `pydantic-core` / `maturin` failures.

No database schema or job-data migration is required.
