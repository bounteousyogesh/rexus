# ServiceNow Custom API — Enhancement Request

## Current API

```
GET /api/ditci/v1/servicenow/incident/{identifier}/detailed
```

### What It Returns Today

The API returns a structured JSON with these sections:

| Section | Fields Returned |
|---------|----------------|
| **incident** | sys_id, number, short_description, description, incident_state, caller_id, location, assignment_group, assigned_to, category, subcategory, priority, impact, urgency, cmdb_ci, opened_at, opened_by, closed_at, u_correction, u_related_project, company |
| **notes** | work_notes (array of individual entries with value, created_by, created_on), comments, watch_list |
| **resolution** | close_code, close_notes, u_resolution_category, u_resolution_sub_category, u_resolved_at |
| **related_records** | parent_incident, problem_id, rfc (change), u_fix_change |
| **vendor** | vendor ticket, vendor contact, vendor open/resolved/closed dates |
| **order_data** | u_order_number, u_order_type, u_order_date, u_total_order_amount, u_correction_type, u_error_category, u_financial_impact |
| **it_comms** | comms type, incident manager, technical manager |
| **ms_teams** | chat id, members, history |
| **external_system** | external system id, key, URL, journal IDs |

---

## What We Need Added

The following fields are available on the incident table but not returned by this API. We need them for building the incident intelligence system.

### Operational Metrics

| Field | Table Column | Why We Need It |
|-------|-------------|----------------|
| **Business duration** | `business_duration` | How long the resolution took in business hours (e.g., "3 Hours 16 Minutes"). Critical for playbook — tells engineers how long this type of issue typically takes. |
| **Business seconds** | `business_stc` | Numeric version of business duration for aggregation and comparison. |
| **Calendar duration** | `calendar_duration` | Total wall-clock time from open to close. |
| **Reassignment count** | `reassignment_count` | How many teams touched this incident. Indicates complexity — higher count means harder problem. |
| **Reopen count** | `reopen_count` | How many times this was reopened. Indicates resolution quality. |
| **Made SLA** | `made_sla` | Whether the incident met its SLA target. |
| **Escalation level** | `escalation` | Current escalation level (Normal, Overdue, etc.). |
| **Severity** | `severity` | Operational severity rating. |

### Resolution Details

| Field | Table Column | Why We Need It |
|-------|-------------|----------------|
| **Resolved by** | `u_resolved_by` | Who actually fixed the issue (not just who's assigned). Helps identify subject matter experts per problem type. |
| **Resolution confirmed by** | `u_resolution_confirmed_by` | Who validated the fix. |
| **Closed by** | `closed_by` | Who closed the ticket. |

### JIRA Integration

| Field | Table Column | Why We Need It |
|-------|-------------|----------------|
| **JIRA number** | `u_jira_number` | The linked JIRA ticket (e.g., OPOS-1087). Currently we extract this from close_notes text via regex — having it as a structured field is more reliable. |

### Contact Details

| Field | Table Column | Why We Need It |
|-------|-------------|----------------|
| **Contact type / Channel** | `contact_type` | How the incident was reported (Self-service, Email, Phone). Useful for analytics. |
| **Opened by** | `opened_by` | Who created the incident (display name). |

---

## Summary

**8 operational fields** + **3 resolution fields** + **1 JIRA field** + **2 contact fields** = **14 additional fields** needed.

All of these exist on the incident table today. They just need to be included in the API response.

### Suggested Response Addition

Add a new section to the existing response:

```json
{
  "incident": { ... existing fields ... },
  "notes": { ... },
  "resolution": {
    ... existing fields ...,
    "u_resolved_by": "Mrutunjay Pandit",
    "u_resolved_by_display": "Mrutunjay Pandit",
    "u_resolution_confirmed_by": "Yogesh Naik",
    "u_resolution_confirmed_by_display": "Yogesh Naik",
    "closed_by": "Jagadeesan Ellappalayam Sivasamy",
    "closed_by_display": "Jagadeesan Ellappalayam Sivasamy"
  },
  "related_records": {
    ... existing fields ...,
    "u_jira_number": "OPOS-1087"
  },
  "operational_metrics": {
    "business_duration": "3 Hours 16 Minutes",
    "business_stc": 11798,
    "calendar_duration": "8 Hours 33 Minutes",
    "reassignment_count": 3,
    "reopen_count": 0,
    "made_sla": true,
    "escalation": "Normal",
    "severity": "3 - Low"
  },
  "contact": {
    "contact_type": "Self-service",
    "contact_type_display": "Self-service",
    "opened_by": "Vyshnavi Bhupathiraju",
    "opened_by_display": "Vyshnavi Bhupathiraju"
  },
  "order_data": { ... existing fields ... },
  ...
}
```

No changes to existing fields or structure — just additions.
