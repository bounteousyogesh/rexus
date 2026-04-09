"""
REX-US — Shared text cleaning utilities.

QUAL-002: Canonical clean_for_embedding extracted from sync.py (stricter PII stripping).
Both analyze.py and sync.py should import from here to avoid drift.
"""

import re

# Generic/filler words to remove before embedding
GENERIC_WORDS = {
    "issue", "issues", "error", "errors", "problem", "problems",
    "fix", "fixed", "fixing", "resolve", "resolved", "resolving",
    "ticket", "incident", "please", "help", "needed", "request",
    "update", "updated", "updating", "closing", "closed",
}


def clean_for_embedding(text: str, strict: bool = False) -> str:
    """
    Normalize text for embedding generation.

    Args:
        text: Raw text to clean.
        strict: If True, uses stricter PII stripping (removes phone numbers,
                emails, and strips identifiers entirely instead of replacing
                with placeholders). Used by sync.py for bulk import.
                If False, replaces identifiers with placeholders like [ORDER],
                [SITE], [INC], [PRB]. Used by analyze.py for analysis.

    Returns:
        Cleaned text string.
    """
    if not text:
        return ""

    if strict:
        # Strict mode: remove identifiers entirely (sync.py behavior)
        text = re.sub(r'\b\d{10}\b', '', text)
        text = re.sub(r'\b[A-Z]{2,3}\s*[-_]?\s*\d{2}\b', '', text)
        text = re.sub(r'\$\s*[\d,]+\.?\d*', '', text)
        text = re.sub(r'\bINC\d+\b', '', text)
        text = re.sub(r'\bPRB\d+\b', '', text)
        text = re.sub(r'\bINCTASK\d+\b', '', text)
        text = re.sub(r'\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b', '', text)
        # PII: phone numbers and email addresses
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '', text)
        text = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '', text)
        # Remove generic filler words
        words = text.split()
        words = [w for w in words if w.lower().strip(".,;:!?()") not in GENERIC_WORDS]
        return re.sub(r'\s+', ' ', ' '.join(words)).strip()
    else:
        # Standard mode: replace with placeholders (analyze.py behavior)
        text = re.sub(r'\b\d{10}\b', '[ORDER]', text)
        text = re.sub(r'\b[A-Z]{2,3}\s+\d{2}\b', '[SITE]', text)
        text = re.sub(r'\$\s*[\d,]+\.?\d*', '$[AMOUNT]', text)
        text = re.sub(r'\bINC\d+\b', '[INC]', text)
        text = re.sub(r'\bPRB\d+\b', '[PRB]', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
