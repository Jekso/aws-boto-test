from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401
from street_incident_ai.config import load_app_config
from street_incident_ai.logging_config import setup_logging
from street_incident_ai.salesforce_client import SalesforceCaseClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Salesforce OAuth token only.")
    parser.add_argument("--env", default=".env")
    args = parser.parse_args()

    config = load_app_config(args.env)
    setup_logging(level=config.log_level)
    client = SalesforceCaseClient(
        token_url=config.salesforce_token_url,
        case_url=config.salesforce_case_url,
        client_id=config.salesforce_client_id,
        client_secret=config.salesforce_client_secret,
        dry_run=config.dry_run_salesforce,
    )
    token = client.obtain_token(force_refresh=True)
    safe = token.raw.copy()
    if "access_token" in safe:
        safe["access_token"] = safe["access_token"][:12] + "..."
    print(json.dumps(safe or {"dry_run": True, "token_type": token.token_type}, indent=2))


if __name__ == "__main__":
    main()
