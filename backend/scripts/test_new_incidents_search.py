"""
Probe ServiceNow for today's New-state incidents.

Usage (from repo root):
    py backend/scripts/test_new_incidents_search.py
    py backend/scripts/test_new_incidents_search.py --verbose
    py backend/scripts/test_new_incidents_search.py --date 2026-07-02
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))

from backend.services.servicenow_client import ServiceNowClient
from backend.api.routers.sync.sync import is_incident_state

def _print_incidents(label: str, incidents: list, verbose: bool) -> None:
    print(f"\n{label}: {len(incidents)} incident(s)")
    for inc in incidents[:10]:
        num = inc.get("number") or inc.get("incident_number") or "?"
        state = inc.get("incident_state_display") or inc.get("incident_state") or "?"
        opened = inc.get("opened_at") or inc.get("sys_created_on") or "?"
        sd = (inc.get("short_description") or "")[:60]
        print(f"  {num} | {state} | opened={str(opened)[:19]} | {sd}")
    if len(incidents) > 10:
        print(f"  ... and {len(incidents) - 10} more")
    if verbose and incidents:
        print(json.dumps(incidents[0], indent=2, default=str)[:2000])

def _try_search(client: ServiceNowClient, label: str, verbose: bool, **kwargs) -> list:
    print(f"\n--- {label} ---")
    print(f"params: {kwargs}")
    try:
        incidents = client.search_incidents(**kwargs)
        _print_incidents("OK", incidents, verbose)
        return incidents
    except Exception as e:
        print(f"FAILED: {e}")
        return []

def main() -> int:
    parser = argparse.ArgumentParser(description="Test SN search for new incidents today")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    today = args.date or date.today().strftime("%Y-%m-%d")
    start = f"{today} 00:00:00"
    end = f"{today} 23:59:59"

    print(f"Instance: {__import__('os').getenv('SERVICENOW_INSTANCE', '(unset)')}")
    print(f"Date window: {start} to {end}")

    client = ServiceNowClient()

    # Primary: date-only search (same as get_new_incidents), then client New-state filter
    primary = _try_search(
        client,
        "Primary (date window only)",
        args.verbose,
        start_date=start,
        end_date=end,
    )
    if primary:
        new_only = [i for i in primary if is_incident_state(i, "new")]
        _print_incidents("Client-filtered New from date window", new_only, args.verbose)

    if not primary:
        try:
            all_open = client.search_incidents(
                start_date=start, end_date=end
            )
            new_only = [i for i in all_open if is_incident_state(i, "new")]
            _print_incidents("Client-filtered New from date window", new_only, args.verbose)
        except Exception as e:
            print(f"Fallback failed: {e}")

    # Helper used by app
    print("\n--- get_new_incidents() ---")
    try:
        app_result = client.get_new_incidents()
        _print_incidents("App helper", app_result, args.verbose)
    except Exception as e:
        print(f"FAILED: {e}")
        return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
