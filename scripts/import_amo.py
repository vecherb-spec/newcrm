"""Import amoCRM deals JSON into Medialive CRM.

Usage:
    CRM_API_URL=http://localhost:8000/api/v1 CRM_API_TOKEN=svc_... \
      python scripts/import_amo.py amo_deals.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Import amoCRM deals into Medialive CRM")
    parser.add_argument("file", type=Path, help="JSON file with amoCRM deals")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("CRM_API_URL", "http://localhost:8000/api/v1"),
        help="CRM API base URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CRM_API_TOKEN"),
        help="Bearer service API token",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate import without writing data",
    )
    args = parser.parse_args()
    if not args.token:
        parser.error("Pass --token or set CRM_API_TOKEN")

    with args.file.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    response = httpx.post(
        f"{args.api_url.rstrip('/')}/imports/amo/deals",
        params={"dry_run": str(args.dry_run).lower()},
        headers={"Authorization": f"Bearer {args.token}"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
