# REX-US — End User Guide

## What is REX-US?

REX-US is an AI-powered assistant that helps you resolve ServiceNow incidents faster. When you upload a new incident, REX-US:

1. Finds the most similar past incidents from the knowledge base
2. Suggests which Problem record to tag the incident to
3. Generates a step-by-step playbook based on how similar incidents were actually resolved
4. Provides detailed resolution notes with evidence from past investigations

REX-US does not auto-resolve or auto-tag. It provides suggestions that you review and act on.

---

## Getting Started

Open REX-US in your browser. You'll see the navigation bar with these tabs:

- **Dashboard** — overview of the knowledge base (incident counts, categories, systems, resolution times)
- **Analyze** — upload an incident for AI-powered analysis (this is the main feature)
- **SN Sync** — import new incidents from ServiceNow into the knowledge base
- **Incidents** — browse and search all incidents in the knowledge base
- **Clusters** — view incident groups (similar incidents clustered together)
- **Search** — free-text semantic search across all incidents

---

## Analyzing an Incident

This is the core workflow — what you'll use most.

### Option 1: Upload a PDF

1. Go to the **Analyze** tab
2. Click **Upload PDF**
3. Select the ServiceNow incident PDF exported from your browser
4. REX-US extracts the fields automatically and runs the analysis

### Option 2: Paste JSON

1. Go to the **Analyze** tab
2. Click **JSON Paste**
3. Paste the ServiceNow incident JSON (from the API or copied from the ticket)
4. Click **Analyze**

### Option 3: Quick Text

1. Go to the **Analyze** tab
2. Click **Quick Text**
3. Type or paste a brief description of the issue (e.g., "GK POS frozen on Please Wait screen at store AZ 14")
4. Click **Analyze**

### What You Get Back

After ~15 seconds, REX-US returns:

**Confidence Score** — How confident the system is in its analysis (0-100%). Higher means more similar incidents were found.

**Problem Suggestion** — The recommended Problem record to tag this incident to, with:
- Problem ID (e.g., PRB0015628)
- How many similar incidents are tagged to this problem
- Whether the problem is Open or Cancelled
- A secondary suggestion if available

**Playbook** — A concise, step-by-step resolution guide:
- What the issue pattern is
- The most likely fix (with incident references)
- Step-by-step instructions from past resolutions
- What to do if the primary fix doesn't work
- Who to escalate to

**Resolution Notes** — Detailed evidence:
- What the team has done for similar incidents
- What the team has requested (escalations, JIRA tickets)
- A reference table of all similar incidents with dates, order IDs, and similarity scores

**Similar Incidents** — The top matching incidents from the knowledge base, with their close notes and similarity scores.

### Reading the Results

- **Confidence > 80%**: Strong match — the playbook is highly relevant
- **Confidence 60-80%**: Good match — review the similar incidents to confirm relevance
- **Confidence < 60%**: Weak match — the incident may be a new pattern not well represented in the knowledge base

The playbook cites specific incident numbers (e.g., [INC2061899]) for every claim. You can look up these incidents in the Incidents tab to see the full details.

---

## Providing Feedback

After each analysis, you'll see a feedback section at the bottom.

**Text Feedback:** Type what was helpful, what was wrong, or what was missing. This helps improve future suggestions.

**Voice Feedback:** Click the microphone button, speak your feedback, and it will be transcribed automatically.

**Rating:** Rate the analysis 1-5 stars.

Your feedback is linked to the specific analysis and stored for review. It directly influences how the system improves over time.

---

## Browsing Incidents

The **Incidents** tab lets you browse all incidents in the knowledge base.

- **Search**: Type any keyword to search across incident descriptions
- **Filter by category**: Select a category to narrow results
- **Filter by system (CMDB CI)**: Select a system to see only incidents for that system
- **Click any incident** to see full details in a side panel

---

## Importing New Incidents (SN Sync)

The **SN Sync** tab connects to ServiceNow and checks for new closed incidents.

1. Click **Check for New Incidents** — the system queries ServiceNow for closed incidents not yet in the knowledge base
2. Results are grouped by month and week
3. Click **Import** on any group to pull those incidents in (fetch details, generate embeddings, add to knowledge base)
4. Imported incidents are immediately available for future analyses

This is typically done weekly or monthly to keep the knowledge base current.

---

## Tips for Best Results

- **Include as much detail as possible** — the more information in the incident (description, CMDB CI, category), the better the match
- **PDF upload gives the richest data** — it captures all fields from the ServiceNow form
- **Quick Text works for fast lookups** — but will have lower confidence since there's less context to match on
- **Check the similar incidents** — even if the problem suggestion isn't perfect, the similar incidents often contain the resolution you need
- **Give feedback** — it takes 10 seconds and directly improves the system for everyone

---

## FAQ

**Q: Does REX-US change anything in ServiceNow?**
A: No. REX-US only reads from ServiceNow. It never writes back, creates tickets, or modifies any data.

**Q: Can I use REX-US for open/active incidents?**
A: Yes. Upload any incident — open or closed. REX-US finds similar past incidents regardless of the current ticket's state.

**Q: Why does the system sometimes suggest a Cancelled problem?**
A: The system prioritizes Open problems, but if the best match is to a Cancelled problem, it will still show it as reference. You should tag to the nearest Open problem instead.

**Q: How often is the knowledge base updated?**
A: Through the SN Sync tab, typically weekly. Every incident you analyze is also automatically added to the knowledge base (progressive learning).

**Q: Is my data sent to OpenAI?**
A: Yes — incident descriptions are sent to OpenAI for embedding and playbook generation. However, PII (names, phone numbers, emails, order numbers) is stripped before sending. Work notes are never sent. See the Security README for full details.

---

*REX-US v7 | User Guide v1.0*
