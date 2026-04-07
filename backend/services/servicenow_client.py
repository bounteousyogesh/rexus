"""
REX-US — ServiceNow Client

OAuth 2.0 client for DT's ServiceNow instance.
Handles token management, incident fetching, and work note retrieval.
"""

import os
import time
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

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

        self._token: Optional[str] = None
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

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
        }

    # ── Table API ─────────────────────────────────────────────────────

    def query_table(
        self,
        table: str,
        query: str = "",
        fields: List[str] = None,
        limit: int = 100,
        offset: int = 0,
        display_value: bool = True,
    ) -> List[Dict[str, Any]]:
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

    # ── Detailed API ──────────────────────────────────────────────────

    def get_incident_detailed(self, incident_number: str) -> Optional[Dict[str, Any]]:
        """Fetch full incident with work notes via DT custom API."""
        resp = requests.get(
            f"{self.instance_url}/api/ditci/v1/servicenow/incident/{incident_number}/detailed",
            headers=self._headers(),
            timeout=self._timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("result", {}).get("success"):
                return data["result"]["data"]
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
        fields: List[str] = None,
    ) -> List[Dict[str, Any]]:
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

    def fetch_work_notes(self, sys_id: str) -> List[Dict[str, Any]]:
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
