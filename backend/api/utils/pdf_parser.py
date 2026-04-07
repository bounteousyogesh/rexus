"""
REX-US PDF Parser — Extracts structured fields from ServiceNow incident PDFs.
Ported from NEXUS with improvements.
"""

import re
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


# Known ServiceNow field labels for high-precision matching
COMMON_FIELDS = [
    "Caller", "Phone", "Location", "Number", "Opened", "Opened by",
    "Current status", "Incident state", "Assignment group", "Assigned to",
    "Category", "Subcategory", "Configuration item", "Detected date",
    "Follow up Date", "GK POS Component", "Affected Version",
    "Related project", "Impact", "Urgency", "Priority", "Major Incident",
    "Template", "Correction", "Requested By", "Channel", "Vendor",
    "Send to Vendor", "Describe CI", "Post-Incident Review", "Parent Ticket",
    "Company", "Resolved", "Feedback Type", "child incidents",
    "Resolution code", "Resolution Category", "Resolution Sub Category",
    "Resolution notes", "Short description", "Description",
    "Close notes", "Close code", "Closed", "Closed by",
    "Business service", "Select Escalation Reason Tier 1",
    "Select Escalation Reason Tier 2",
]

# Broken words from PDF extraction
BROKEN_WORDS = {
    r'\bminu\s+tes\b': 'minutes',
    r'\bhou\s+rs?\b': 'hours',
    r'\bsec\s+onds?\b': 'seconds',
    r'\bcom\s+plete\s*d?\b': 'completed',
    r'\bcan\s+celle\s*d?\b': 'cancelled',
    r'\bres\s+oluti\s+on\b': 'resolution',
    r'\bassi\s+gn\s*ment\b': 'assignment',
    r'\bdesc\s+ription\b': 'description',
    r'\bmana\s+gement\b': 'management',
    r'\bbusi\s+ness\b': 'business',
}


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip())
    for pattern, replacement in BROKEN_WORDS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Fix broken INC/PRB numbers
    text = re.sub(r'\binc\s+(\d+)\b', r'INC\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprb\s+(\d+)\b', r'PRB\1', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(INC|PRB|INCTASK)\s*(\d+)\s+(\d+)\s*(\d*)\b', r'\1\2\3\4', text, flags=re.IGNORECASE)
    return text.strip()


def is_irrelevant_line(line: str) -> bool:
    if not line or len(line.strip()) < 2:
        return True
    lower = line.lower()
    return any(x in lower for x in [
        'page ', 'run by', 'run date', 'incident details page',
        'report title', 'table name', 'query condition', 'sort order',
        'related list title',
    ])


def extract_field_value_pairs(text: str) -> dict:
    fields = {}
    common_pattern = '|'.join(re.escape(f) for f in COMMON_FIELDS)
    for line in text.split('\n'):
        line = line.strip()
        if is_irrelevant_line(line) or not line:
            continue

        positions = []
        # Match known fields first
        for match in re.finditer(rf'\b({common_pattern}):\s*', line, re.IGNORECASE):
            positions.append((match.start(), match.end(), match.group(1).strip()))
        # Then general pattern
        for match in re.finditer(r'([A-Z][A-Za-z\s\(\)\-]{0,30}?):\s+(?![0-9])', line):
            name = match.group(1).strip()
            if len(name) > 35 or len(name.split()) > 3:
                continue
            overlap = any(match.start() >= s and match.start() < e for s, e, _ in positions)
            if not overlap:
                positions.append((match.start(), match.end(), name))

        positions.sort(key=lambda x: x[0])

        for i, (start, end, field) in enumerate(positions):
            if len(field) < 2:
                continue
            next_start = positions[i + 1][0] if i + 1 < len(positions) else len(line)
            value = clean_text(line[end:next_start])
            if value and (field not in fields or len(value) > len(fields[field])):
                fields[field] = value

    return fields


def extract_work_notes(text: str) -> list[str]:
    notes = []
    current = []
    in_section = False
    for line in text.split('\n'):
        line = line.strip()
        if 'work notes' in line.lower():
            in_section = True
            continue
        if in_section:
            if re.match(r'^\d{4}-\d{2}-\d{2}', line):
                if current:
                    notes.append(' '.join(current))
                    current = []
                current.append(line)
            elif current:
                current.append(line)
    if current:
        notes.append(' '.join(current))
    return notes


class PDFParser:
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

    def extract(self) -> dict:
        raw_text = ""
        all_fields = {}
        tables_data = []

        if HAS_PDFPLUMBER:
            raw_text, all_fields, tables_data = self._extract_pdfplumber()
        elif HAS_PYMUPDF:
            raw_text, all_fields = self._extract_pymupdf()
        else:
            raise ImportError("Install pdfplumber or pymupdf")

        work_notes = extract_work_notes(raw_text)
        return self._organize(all_fields, work_notes, tables_data, raw_text)

    def _extract_pdfplumber(self):
        all_text = ""
        tables = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text = re.sub(r'Incident Details Page \d+\n', '', text)
                    text = re.sub(r'Run By :.*?Mountain Standard Time\n?', '', text)
                    all_text += "\n" + text
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
        fields = extract_field_value_pairs(all_text)
        return all_text, fields, tables

    def _extract_pymupdf(self):
        all_text = ""
        doc = fitz.open(self.pdf_path)
        for page in doc:
            text = page.get_text()
            if text:
                text = re.sub(r'Incident Details Page \d+\n', '', text)
                all_text += "\n" + text
        doc.close()
        fields = extract_field_value_pairs(all_text)
        return all_text, fields

    def _organize(self, fields: dict, work_notes: list, tables: list, raw_text: str) -> dict:
        # Extract short description and description from raw text if not in fields
        short_desc = fields.get("Short description", "")
        if not short_desc:
            m = re.search(r'Short description:\s*(.+?)(?:\n|Description:)', raw_text, re.IGNORECASE | re.DOTALL)
            if m:
                short_desc = clean_text(m.group(1))

        description = fields.get("Description", "")
        if not description:
            m = re.search(r'(?:^|\n)\s*Description:\s*\n\s*([^\n]+)', raw_text, re.IGNORECASE | re.MULTILINE)
            if m and m.group(1).strip() != short_desc:
                description = clean_text(m.group(1))

        # Extract key details from raw text that field extraction misses
        # These are critical for distinguishing sub-patterns
        idoc_text = ""
        m = re.search(r'IDoc\s*Text\s*:\s*(.+?)(?:\n|$)', raw_text, re.I)
        if m:
            idoc_text = clean_text(m.group(1))

        initial_finding = ""
        m = re.search(r'Initial\s*(?:analysis\s*)?[Ff]inding[s]?\s*:\s*(.+?)(?:\n|$)', raw_text, re.I)
        if m and len(m.group(1).strip()) > 3:
            initial_finding = clean_text(m.group(1))

        error_category = fields.get("Error Category", "")
        if not error_category:
            m = re.search(r'Error\s*Category\s*:\s*\n?\s*(.+?)(?:\n|$)', raw_text, re.I)
            if m and len(m.group(1).strip()) > 2:
                error_category = clean_text(m.group(1))

        idoc_number = ""
        m = re.search(r'IDoc\s*Number\s*:\s*(\d+)', raw_text, re.I)
        if m:
            idoc_number = m.group(1)

        pos_event = ""
        m = re.search(r'POS\s*Event\s*:\s*(.+?)(?:\n|$)', raw_text, re.I)
        if m and len(m.group(1).strip()) > 1:
            pos_event = clean_text(m.group(1))

        # Extract additional comments block
        additional_comments = fields.get("Additional comments (shared)", "")
        if not additional_comments:
            m = re.search(r'Additional comments \(shared\):\s*\n(.+?)(?:\nWork notes:)', raw_text, re.DOTALL | re.I)
            if m:
                additional_comments = m.group(1).strip()[:500]

        return {
            "pdf_fields": {
                "Short description": short_desc,
                "Description": description,
            },
            "incident_section": {
                k: fields.get(k, "") for k in [
                    "Number", "Current status", "Incident state", "Caller",
                    "Category", "Subcategory", "Priority", "Impact", "Urgency",
                    "Assignment group", "Assigned to", "Configuration item",
                    "Opened", "Opened by", "Channel", "Requested By",
                    "Major Incident", "Parent Ticket", "Company",
                    "GK POS Component", "Related project",
                ]
            },
            "resolution_information_section": {
                k: fields.get(k, "") for k in [
                    "Resolution code", "Resolution Category", "Resolution Sub Category",
                    "Resolution notes", "Close notes", "Close code",
                    "Closed", "Closed by", "Resolved",
                ]
            },
            "related_records_section": {
                "Parent Incident": fields.get("Parent Incident", ""),
                "Problem": fields.get("Problem", ""),
                "Cause Change": fields.get("Cause Change", ""),
                "Fix Change": fields.get("Fix Change", ""),
            },
            "notes_section": {
                "Work notes": work_notes,
                "Additional comments": additional_comments,
            },
            "incident_details": {
                "IDoc Text": idoc_text,
                "IDoc Number": idoc_number,
                "Initial Finding": initial_finding,
                "Error Category": error_category,
                "POS Event": pos_event,
            },
            "extraction_timestamp": datetime.now().isoformat(),
            "extraction_method": "pdfplumber" if HAS_PDFPLUMBER else "pymupdf",
        }
