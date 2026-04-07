"""
REX-US — ServiceNow Custom API Response Validator

Tests the /api/ditci/v1/servicenow/incident/{identifier}/detailed endpoint
and validates that all required fields are present in the response.

Usage:
    python test_api_response.py INC2091685
    python test_api_response.py INC2091685 INC2055983 INC2085173
    python test_api_response.py INC2091685 --verbose
"""

import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.services.servicenow_client import ServiceNowClient

# ═══════════════════════════════════════════════════════════════════
# Expected fields — what the API should return
# ═══════════════════════════════════════════════════════════════════

EXPECTED = {
    "incident": {
        "existing": [
            "sys_id", "number", "short_description", "description",
            "incident_state", "caller_id", "location",
            "assignment_group", "assigned_to",
            "category", "subcategory", "priority", "impact", "urgency",
            "cmdb_ci", "opened_at", "opened_by", "closed_at",
            "u_correction", "u_related_project", "company",
        ],
        "new": [],  # no new fields needed in incident section
    },
    "notes": {
        "existing": ["work_notes", "comments"],
        "new": [],
    },
    "resolution": {
        "existing": [
            "close_code", "close_notes",
            "u_resolution_category", "u_resolution_sub_category",
        ],
        "new": [
            "u_resolved_by",
            "u_resolution_confirmed_by",
            "closed_by",
        ],
    },
    "related_records": {
        "existing": ["parent_incident", "problem_id", "rfc", "u_fix_change"],
        "new": [
            "u_jira_number",
        ],
    },
    "operational_metrics": {
        "existing": [],  # this is a new section entirely
        "new": [
            "business_duration",
            "business_stc",
            "calendar_duration",
            "reassignment_count",
            "reopen_count",
            "made_sla",
            "escalation",
            "severity",
        ],
    },
    "contact": {
        "existing": [],  # this is a new section entirely
        "new": [
            "contact_type",
            "opened_by",
        ],
    },
    "order_data": {
        "existing": [
            "u_order_number", "u_order_type", "u_order_date",
            "u_total_order_amount", "u_correction_type",
            "u_error_category", "u_financial_impact",
        ],
        "new": [],
    },
}


def validate_response(incident_number: str, client: ServiceNowClient, verbose: bool = False):
    """Validate a single incident response against expected fields."""

    print(f"\n{'='*60}")
    print(f"  Testing: {incident_number}")
    print(f"{'='*60}")

    # Fetch
    data = client.get_incident_detailed(incident_number)
    if not data:
        print(f"  FAIL — API returned no data for {incident_number}")
        print(f"         Check if incident exists and API is accessible.")
        return {"status": "FAIL", "reason": "no_data"}

    total_pass = 0
    total_fail = 0
    total_new_pass = 0
    total_new_fail = 0
    missing_fields = []

    for section_name, fields in EXPECTED.items():
        section_data = data.get(section_name, {})
        section_exists = section_name in data

        # Check existing fields
        for field in fields["existing"]:
            if section_exists and field in section_data:
                total_pass += 1
                if verbose:
                    val = section_data[field]
                    display = str(val)[:50] if val else "(empty)"
                    print(f"  PASS  {section_name}.{field}: {display}")
            else:
                total_fail += 1
                missing_fields.append(f"{section_name}.{field} (existing)")
                if verbose:
                    print(f"  FAIL  {section_name}.{field} — MISSING")

        # Check new/enhanced fields
        for field in fields["new"]:
            # Check in the expected section first
            found = False
            found_in = None

            if section_exists and field in section_data:
                found = True
                found_in = section_name
            else:
                # Also check if it's been added to a different section
                for alt_section, alt_data in data.items():
                    if isinstance(alt_data, dict) and field in alt_data:
                        found = True
                        found_in = alt_section
                        break
                    # Check display value variants
                    if isinstance(alt_data, dict) and f"{field}_display" in alt_data:
                        found = True
                        found_in = alt_section
                        break

            if found:
                total_new_pass += 1
                if verbose:
                    val = data.get(found_in, {}).get(field, "")
                    display = str(val)[:50] if val else "(empty)"
                    loc = f" (found in '{found_in}')" if found_in != section_name else ""
                    print(f"  PASS  {section_name}.{field}: {display}{loc}")
            else:
                total_new_fail += 1
                missing_fields.append(f"{section_name}.{field} (NEW — enhancement request)")
                if verbose:
                    print(f"  FAIL  {section_name}.{field} — NOT FOUND (enhancement needed)")

    # Summary
    print(f"\n  --- Results for {incident_number} ---")
    print(f"  Existing fields:    {total_pass} pass / {total_fail} fail")
    print(f"  New fields:         {total_new_pass} pass / {total_new_fail} fail")
    print(f"  Total:              {total_pass + total_new_pass} pass / {total_fail + total_new_fail} fail")

    if missing_fields:
        print(f"\n  Missing fields ({len(missing_fields)}):")
        for f in missing_fields:
            print(f"    - {f}")

    status = "PASS" if (total_fail == 0 and total_new_fail == 0) else "PARTIAL" if total_new_fail > 0 and total_fail == 0 else "FAIL"
    print(f"\n  Status: {status}")

    return {
        "status": status,
        "incident": incident_number,
        "existing_pass": total_pass,
        "existing_fail": total_fail,
        "new_pass": total_new_pass,
        "new_fail": total_new_fail,
        "missing": missing_fields,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate ServiceNow custom API response against expected fields"
    )
    parser.add_argument("incidents", nargs="+", help="Incident numbers to test (e.g., INC2091685)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all field checks")
    args = parser.parse_args()

    client = ServiceNowClient()
    print(f"Connected to: {client.instance_url}")

    results = []
    for inc in args.incidents:
        result = validate_response(inc, client, verbose=args.verbose)
        results.append(result)

    # Final summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")

    for r in results:
        icon = {"PASS": "✓", "PARTIAL": "≈", "FAIL": "✗"}.get(r["status"], "?")
        print(f"  {icon} {r['incident']}: {r['status']} "
              f"(existing: {r['existing_pass']}/{r['existing_pass']+r['existing_fail']}, "
              f"new: {r['new_pass']}/{r['new_pass']+r['new_fail']})")

    all_missing = set()
    for r in results:
        all_missing.update(r.get("missing", []))

    new_missing = [f for f in all_missing if "enhancement" in f.lower()]
    existing_missing = [f for f in all_missing if "existing" in f.lower()]

    if new_missing:
        print(f"\n  Enhancement fields still needed ({len(new_missing)}):")
        for f in sorted(new_missing):
            print(f"    - {f}")

    if existing_missing:
        print(f"\n  WARNING — Existing fields missing ({len(existing_missing)}):")
        for f in sorted(existing_missing):
            print(f"    - {f}")

    if not all_missing:
        print(f"\n  All fields present — API enhancement complete!")


if __name__ == "__main__":
    main()
