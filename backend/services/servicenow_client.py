"""
REX-US — ServiceNow Client

OAuth 2.0 client for DT's ServiceNow instance.
Handles token management, incident fetching, and work note retrieval.
"""

import os
import time
import logging
import requests
from typing import Any
from datetime import date, datetime

logger = logging.getLogger(__name__)

class ServiceNowClient:
    """OAuth 2.0 client for ServiceNow REST API."""

    def __init__(
        self,
        instance_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.instance_url = (instance_url or os.getenv("SERVICENOW_INSTANCE", "")).rstrip("/")
        self.client_id = client_id or os.getenv("SERVICENOW_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("SERVICENOW_CLIENT_SECRET", "")

        if not all([self.instance_url, self.client_id, self.client_secret]):
            raise ValueError("SERVICENOW_INSTANCE, SERVICENOW_CLIENT_ID, SERVICENOW_CLIENT_SECRET are required")

        # SEC-006: Enforce HTTPS to prevent credential transmission in plaintext
        if not self.instance_url.startswith("https://"):
            raise ValueError(
                f"SERVICENOW_INSTANCE must use HTTPS (got: {self.instance_url[:30]}...). "
                "Set SERVICENOW_INSTANCE=https://your-instance.service-now.com"
            )

        self._token: str | None = None
        self._token_expires: float = 0
        self._timeout = int(os.getenv("SERVICENOW_TIMEOUT_S", "30"))

    # ── Auth ──────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        # SEC-012: client_secret is never logged — only the client_id is safe to record.
        resp = requests.post(
            f"{self.instance_url}/oauth_token.do",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 1800)
        # SEC-021: Token acquisition is a routine event — log at DEBUG, not INFO,
        # to avoid polluting production logs with token lifecycle noise.
        logger.debug("ServiceNow OAuth token acquired (client_id=%s)", self.client_id)
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
        }

    # ── Table API ─────────────────────────────────────────────────────

    def query_table(
        self,
        table: str,
        query: str = "",
        fields: list[str] = None,
        limit: int = 100,
        offset: int = 0,
        display_value: bool = True,
    ) -> list[dict[str, Any]]:
        """Query any ServiceNow table with pagination."""
        params = {
            "sysparm_limit": limit,
            "sysparm_offset": offset,
            "sysparm_display_value": str(display_value).lower(),
        }
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = ",".join(fields)

        resp = requests.get(
            f"{self.instance_url}/api/now/table/{table}",
            headers=self._headers(),
            params=params,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

    def count_table(self, table: str, query: str = "") -> int:
        """Get total count matching a query."""
        params = {"sysparm_limit": 1, "sysparm_fields": "sys_id"}
        if query:
            params["sysparm_query"] = query

        resp = requests.get(
            f"{self.instance_url}/api/now/table/{table}",
            headers={**self._headers(), "X-Total-Count": "true"},
            params=params,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return int(resp.headers.get("X-Total-Count", 0))

    # ── DT Search API ────────────────────────────────────────────────

    def search_incidents(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        closed_only: bool | None = None,
        **filters,
    ) -> list[dict[str, Any]]:
        """
        Search incidents using the DT custom search API.
        GET /api/ditci/v1/servicenow/incident/search

        Date params:
            start_date: YYYY-MM-DD (required for date range queries)
            end_date: YYYY-MM-DD (required for date range queries)
            closed_only: true/false; omitted when None (API default applies)

        Filter params (ANDed together):
            category, subcategory, incident_state, caller_id,
            assignment_group, assigned_to, contact_type, cmdb_ci, priority

        Max date range: 6 months per call.
        """
        search_path = os.getenv(
            "SERVICENOW_SEARCH_PATH",
            "/api/ditci/v1/servicenow/incident/search",
        )
        params: dict[str, str] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if closed_only is not None:
            params["closed_only"] = str(closed_only).lower()

        # Add any additional filters
        for k, v in filters.items():
            if v:
                params[k] = str(v)

        resp = requests.get(
            f"{self.instance_url}{search_path}",
            headers=self._headers(),
            params=params,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        # Response: {"result": {"success": true, "data": {"count": N, "incidents": [...]}}}
        if isinstance(data, dict):
            result = data.get("result", {})
            if isinstance(result, dict):
                inner = result.get("data", {})
                if isinstance(inner, dict):
                    return inner.get("incidents", [])
                if isinstance(inner, list):
                    return inner
            if isinstance(result, list):
                return result
        if isinstance(data, list):
            return data
        return []

    def search_incidents_by_months(
        self,
        start_date: str,
        end_date: str,
        closed_only: bool = True,
        **filters,
    ) -> list[dict[str, Any]]:
        """
        Search incidents across a date range that may exceed 6 months.
        Automatically splits into monthly chunks and merges results.

        start_date/end_date: YYYY-MM-DD format.
        """
        from datetime import datetime, timedelta
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        all_incidents = []
        chunk_start = start

        while chunk_start <= end:
            # Each chunk = 1 month
            if chunk_start.month == 12:
                chunk_end = chunk_start.replace(year=chunk_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                chunk_end = chunk_start.replace(month=chunk_start.month + 1, day=1) - timedelta(days=1)
            if chunk_end > end:
                chunk_end = end

            logger.info(f"Searching {chunk_start.strftime('%Y-%m-%d')} → {chunk_end.strftime('%Y-%m-%d')}...")
            incidents = self.search_incidents(
                start_date=chunk_start.strftime("%Y-%m-%d"),
                end_date=chunk_end.strftime("%Y-%m-%d"),
                closed_only=closed_only,
                **filters,
            )
            logger.info(f"  Found {len(incidents)} incidents")
            all_incidents.extend(incidents)

            # Move to next month
            chunk_start = chunk_end + timedelta(days=1)

        return all_incidents

    def get_new_incidents(
        self,
        sync_date: date | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        assignment_group: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search incidents in a date window via the DT search API.

        Pass either a calendar day (sync_date) or an explicit datetime window
        (start/end). Datetime window takes precedence when both are provided.
        New-state filtering is applied by the sync router via is_incident_state.
        Pass ``assignment_group`` to restrict results to a specific group.
        """
        if start is not None and end is not None:
            start_str = start.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end.strftime("%Y-%m-%d %H:%M:%S")
        else:
            day = (sync_date or date.today()).strftime("%Y-%m-%d")
            start_str = f"{day} 00:00:00"
            end_str = f"{day} 23:59:59"

        filters: dict[str, str] = {}
        if assignment_group:
            filters["assignment_group"] = assignment_group

        raw = self.search_incidents(
            start_date=start_str,
            end_date=end_str,
            **filters,
        )
        return raw

    def search_closed_incidents_window(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Discover closed/resolved incidents updated in a datetime window."""
        return self.search_incidents(
            start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
            end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
            closed_only=True,
        )

    # ── Detailed API ──────────────────────────────────────────────────

    def get_incidents_batch_detailed(
        self,
        target_date: str,
        limit: int | None = None,
    ):
        """
        Fetch incidents updated on a given date via DT batch detailed API.
        GET /api/ditci/v1/servicenow/incident/batch/detailed?date=YYYY-MM-DD

        Yields each incident entry (same structure as single detailed endpoint).
        Follows cursor pagination while has_more is true.
        """
        batch_path = os.getenv(
            "SERVICENOW_BATCH_PATH",
            "/api/ditci/v1/servicenow/incident/batch/detailed",
        )
        page_limit = limit or int(os.getenv("SERVICENOW_BATCH_LIMIT", "25"))
        page_limit = max(1, min(page_limit, 100))

        cursor: str | None = None
        while True:
            params: dict[str, str] = {
                "date": target_date,
                "limit": str(page_limit),
            }
            if cursor:
                params["cursor"] = cursor

            resp = requests.get(
                f"{self.instance_url}{batch_path}",
                headers=self._headers(),
                params=params,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            payload = resp.json()

            # Response may be top-level {success, data} or wrapped in result.
            result = payload.get("result", payload) if isinstance(payload, dict) else {}
            if not isinstance(result, dict):
                break
            if result.get("success") is False:
                logger.warning("Batch detailed API returned success=false for %s", target_date)
                break

            data = result.get("data", {})
            if not isinstance(data, dict):
                break

            incidents = data.get("incidents", [])
            if isinstance(incidents, list):
                for entry in incidents:
                    if isinstance(entry, dict):
                        yield entry

            pagination = data.get("pagination", {})
            if not isinstance(pagination, dict):
                break
            if not pagination.get("has_more"):
                break
            cursor = pagination.get("next_cursor")
            if not cursor:
                break

    def get_incident_detailed(self, incident_number: str, include_kb_articles: bool = True) -> dict[str, Any] | None:
        """Fetch full incident with work notes (and attached KB articles) via DT custom API."""
        params = {}
        if include_kb_articles:
            params["include_kb_articles"] = "true"
        resp = requests.get(
            f"{self.instance_url}/api/ditci/v1/servicenow/incident/{incident_number}/detailed",
            headers=self._headers(),
            params=params,
            timeout=self._timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("result", {}).get("success"):
                return data["result"]["data"]
        return None

    def add_incident_comment(
        self,
        identifier: str,
        comment: str,
        *,
        category: str | None = None,
        subcategory: str | None = None,
    ) -> bool:
        """Append a caller-visible comment via PATCH /incident/{identifier}.

        The DT ServiceNow API requires ``category`` and ``subcategory`` in the
        PATCH body when they are not already set on the incident, otherwise it
        returns HTTP 400.  Always include them (using safe fallbacks) so the
        request never fails on a missing field.
        """
        comment = (comment or "").strip()
        if not comment:
            return False
        payload: dict = {
            "comments": comment,
            "category": category or "Software",
            "subcategory": subcategory or "Error Condition",
        }
        logger.info(
            "Posting REXUS comment to SN — incident=%s category=%s subcategory=%s comment_len=%d",
            identifier,
            payload["category"],
            payload["subcategory"],
            len(comment),
        )
        resp = requests.patch(
            f"{self.instance_url}/api/ditci/v1/servicenow/incident/{identifier}",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=self._timeout,
        )
        logger.info(
            "SN comment PATCH response — incident=%s http_status=%s body=%s",
            identifier,
            resp.status_code,
            resp.text[:500],
        )
        if resp.status_code != 200:
            logger.warning(
                "Failed to add comment to %s: HTTP %s %s",
                identifier,
                resp.status_code,
                resp.text[:200],
            )
            return False
        body = resp.json()
        envelope = body.get("result", body)
        if envelope.get("success"):
            logger.info("Posted REXUS comment on %s", identifier)
            return True
        logger.warning(
            "ServiceNow rejected comment on %s: %s",
            identifier,
            envelope.get("message"),
        )
        return False

    def search_incident_by_number(self, incident_number: str, include_kb_articles: bool = True) -> dict[str, Any] | None:
        """Fallback: fetch a single incident via the search API (returns kb_articles too)."""
        search_path = os.getenv("SERVICENOW_SEARCH_PATH", "/api/ditci/v1/servicenow/incident/search")
        params: dict[str, str] = {"number": incident_number}
        if include_kb_articles:
            params["include_kb_articles"] = "true"
        resp = requests.get(
            f"{self.instance_url}{search_path}",
            headers=self._headers(),
            params=params,
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        incidents = data.get("result", {}).get("data", {}).get("incidents", [])
        return incidents[0] if incidents else None

    # ── Knowledge article API ─────────────────────────────────────────

    def get_knowledge_article(self, kb_number: str) -> dict[str, Any] | None:
        """
        Fetch a knowledge article (metadata + optional PDF) via DT custom API.
        Falls back to kb_knowledge table API if custom path is unset or fails.
        """
        kb_number = (kb_number or "").strip().upper()
        if not kb_number:
            return None

        kb_path_template = os.getenv(
            "SERVICENOW_KB_PATH",
            "/api/ditci/v1/servicenow/knowledge/{kb_number}",
        )
        if kb_path_template:
            path = kb_path_template.format(kb_number=kb_number)
            try:
                resp = requests.get(
                    f"{self.instance_url}{path}",
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        result = payload.get("result", payload)
                        if isinstance(result, dict):
                            if result.get("success") and result.get("data"):
                                return result["data"]
                            if result.get("data") and isinstance(result["data"], dict):
                                return result["data"]
                            if "number" in result or "pdf" in result or "short_description" in result:
                                return result
                        if "number" in payload or "pdf" in payload:
                            return payload
            except Exception as e:
                logger.warning("KB custom API failed for %s: %s", kb_number, e)

        try:
            rows = self.query_table(
                "kb_knowledge",
                query=f"number={kb_number}",
                fields=["sys_id", "number", "short_description", "text", "kb_category"],
                limit=1,
            )
            if rows:
                row = rows[0]
                return {
                    "sys_id": row.get("sys_id", ""),
                    "number": row.get("number", kb_number),
                    "short_description": row.get("short_description", ""),
                    "text": row.get("text", ""),
                    "kb_category_display": row.get("kb_category", ""),
                }
        except Exception as e:
            logger.warning("KB table lookup failed for %s: %s", kb_number, e)

        return None

    # ── Convenience ───────────────────────────────────────────────────

    INCIDENT_FIELDS = [
        "sys_id", "number", "short_description", "description",
        "category", "subcategory", "priority", "state",
        "close_notes", "close_code",
        "assignment_group", "assigned_to", "cmdb_ci", "business_service",
        "opened_at", "resolved_at", "closed_at",
        "problem_id", "parent_incident",
    ]

    def fetch_incidents_batch(
        self,
        query: str,
        batch_size: int = 200,
        max_total: int = None,
        fields: list[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch incidents in batches with automatic pagination.
        Yields progress logs.
        """
        fields = fields or self.INCIDENT_FIELDS
        offset = 0
        all_incidents = []

        total = self.count_table("incident", query)
        if max_total:
            total = min(total, max_total)
        logger.info(f"Fetching {total} incidents (batch_size={batch_size})")

        while offset < total:
            remaining = total - offset
            current_batch_size = min(batch_size, remaining)
            batch = self.query_table(
                "incident",
                query=query,
                fields=fields,
                limit=current_batch_size,
                offset=offset,
                display_value=True,
            )
            if not batch:
                break

            all_incidents.extend(batch)
            offset += len(batch)
            pct = len(all_incidents) * 100 // total if total else 0
            logger.info(f"  Progress: {len(all_incidents)}/{total} ({pct}%)")

        logger.info(f"Fetched {len(all_incidents)} incidents total")
        return all_incidents

    def fetch_work_notes(self, sys_id: str) -> list[dict[str, Any]]:
        """Fetch work notes and comments for an incident by sys_id."""
        notes = []

        for element in ["work_notes", "comments"]:
            results = self.query_table(
                "sys_journal_field",
                query=f"element_id={sys_id}^element={element}^ORDERBYDESCsys_created_on",
                fields=["value", "sys_created_by", "sys_created_on", "element"],
                display_value=True,
            )
            for r in results:
                notes.append({
                    "note_type": "work_note" if element == "work_notes" else "comment",
                    "value": r.get("value", ""),
                    "created_by": r.get("sys_created_by", ""),
                    "created_on": r.get("sys_created_on", ""),
                })

        return notes
