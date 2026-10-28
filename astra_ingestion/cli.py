"""Explicit operator commands. No implicit cloud resource creation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .config import Settings
from .models import IngestionSpec
from .store import Store

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    submit = sub.add_parser("submit")
    submit.add_argument("spec_file")
    submit.add_argument("--idempotency-key", required=True)
    status = sub.add_parser("status")
    status.add_argument("job_id", nargs="?")
    args = parser.parse_args()
    settings = Settings.from_env(require_web_auth=False)
    store = Store(settings.database_url, test_mode=settings.test_mode)
    if args.command == "migrate":
        store.migrate()
        result = store.health()
    elif args.command == "submit":
        result = store.submit_job(IngestionSpec.from_dict(json.loads(Path(args.spec_file).read_text())), args.idempotency_key)
    else:
        result = store.get_job(args.job_id) if args.job_id else store.list_jobs()
    print(json.dumps(result, indent=2))
if __name__ == "__main__":
    main()
