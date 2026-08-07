# Release notes

## 1.0.3

- Recovers stale `staged` tasks that still carry a dead worker claim.
- Adds a **Recover** action for running jobs; only tasks beyond the configured stale threshold are released.
- Keeps task, worker and job heartbeats alive during PostgreSQL bulk load and daily-feature generation.
- Auto-refreshes the open job detail window and surfaces stale task diagnostics.
- No database schema migration is required.

## 1.0.1 — Render Python runtime fix

- Pins `PYTHON_VERSION=3.12.7` explicitly for both Render services.
- Makes the build log print the selected Python version.
- Requires prebuilt wheels during dependency installation, preventing unsupported source builds in Render.
- Adds deployment troubleshooting for `pydantic-core` / `maturin` failures.

No database schema or job-data migration is required.
