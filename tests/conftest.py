"""
conftest.py — Shared fixtures for REX-US integration tests.

All tests run against a live backend at BASE_URL (default: http://localhost:8000).
Override by setting the REXUS_BASE_URL environment variable before running pytest.

Usage:
    cd /Users/premkalyan/code/REX-US
    pip install -r tests/requirements.txt
    pytest tests/ -v
"""

import os
import pytest
import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("REXUS_BASE_URL", "http://localhost:8000")

# Timeout for requests that hit OpenAI (analyze, transcribe). The OpenAI
# round-trip can take 10-30 s for GPT-4o completions.
OPENAI_TIMEOUT = float(os.getenv("REXUS_OPENAI_TIMEOUT", "60"))

# Timeout for fast read-only DB queries.
DB_TIMEOUT = float(os.getenv("REXUS_DB_TIMEOUT", "10"))


def _maintenance_auth_headers() -> dict:
    """Headers for POST /sync/import and /kb-mappings/refresh (admin JWT or API key)."""
    headers: dict = {}
    admin_key = os.getenv("REXUS_ADMIN_KEY")
    if admin_key:
        headers["X-Admin-Key"] = admin_key
        return headers

    password = os.getenv("REXUS_ADMIN_PASSWORD", "RexUS@2026!")
    try:
        with httpx.Client(base_url=BASE_URL, timeout=DB_TIMEOUT) as c:
            response = c.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": password},
            )
            if response.status_code == 200:
                token = response.json().get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
    except Exception:
        pass
    return headers


# ---------------------------------------------------------------------------
# Synchronous httpx client fixture (used by the majority of tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """
    A persistent httpx.Client for the entire test session.
    Using session scope keeps connection pooling efficient and avoids per-test
    TCP handshake overhead. Includes admin auth for maintenance POST endpoints.
    """
    with httpx.Client(
        base_url=BASE_URL,
        timeout=DB_TIMEOUT,
        headers=_maintenance_auth_headers(),
    ) as c:
        yield c


@pytest.fixture(scope="session")
def openai_client() -> httpx.Client:
    """
    A separate client with a longer timeout for endpoints that call OpenAI.
    (analyze, analyze/text, search, transcribe)
    """
    with httpx.Client(base_url=BASE_URL, timeout=OPENAI_TIMEOUT) as c:
        yield c


# ---------------------------------------------------------------------------
# Reusable test data payloads
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def minimal_ticket_json() -> dict:
    """
    Smallest valid ServiceNow-style JSON accepted by POST /api/v1/analyze.
    Uses only pdf_fields which is the minimum path through build_embedding_text.
    """
    return {
        "ticket_json": {
            "pdf_fields": {
                "Short description": "Vision order not processing after store close",
                "Description": "Order 5001234567 failed to sync to Vision after the nightly close process ran.",
            },
            "incident_section": {
                "Category": "Software",
                "Subcategory": "Application",
                "Configuration item": "Vision",
            },
            "resolution_information_section": {
                "Close notes": "Resent WE19 IDoc and order processed successfully.",
            },
        }
    }


@pytest.fixture(scope="session")
def full_ticket_json() -> dict:
    """
    A more complete ServiceNow incident JSON that exercises all build_embedding_text paths.
    """
    return {
        "ticket_json": {
            "pdf_fields": {
                "Short description": "POS terminal unable to finalize transaction at store checkout",
                "Description": "GK POS terminal at store TX 01 is throwing APCR error during card payment finalization.",
            },
            "incident_section": {
                "Number": "INC9990001",
                "Category": "Hardware",
                "Subcategory": "Point of Sale",
                "Configuration item": "GK POS",
                "Assignment group": "Store Technology Support",
                "Caller": "store.manager@example.com",
                "Location": "TX 01",
                "Priority": "2 - High",
            },
            "resolution_information_section": {
                "Close notes": "Force closed the POS terminal, restarted poslog service, transaction completed.",
            },
            "incident_details": {
                "IDoc Text": "WE19 resend triggered",
                "Initial Finding": "APCR timeout during card authorization",
                "Error Category": "Payment Gateway Timeout",
                "POS Event": "CHECKOUT_FAILED",
            },
        },
        "limit": 10,
        "threshold": 0.35,
    }


@pytest.fixture(scope="session")
def minimal_pdf_bytes() -> bytes:
    """
    A minimal syntactically-valid PDF (13 objects, renders as blank page).
    Sufficient to pass the %PDF- magic-byte and size checks in /parse-pdf.
    """
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000062 00000 n \n0000000119 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
    )
