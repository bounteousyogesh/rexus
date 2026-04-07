# ServiceNow Custom API — Enhancement Request #2

## Endpoint

```
GET /api/ditci/v1/servicenow/incident/{identifier}/detailed
```

## Request

Add the **problem record state** to the existing `related_records` section of the response.

Currently, the API returns the problem ID but not its state:

```json
"related_records": {
    "parent_incident": "",
    "problem_id": "03ac7d7d878c62d0d7a676e9cebb356f",
    "problem_id_display": "PRB0015676",
    "rfc": "",
    "u_fix_change": "",
    "u_jira_number": "OPOS-1087"
}
```

### What We Need Added

Two new fields in `related_records`:

| Field | Source | Example Value |
|-------|--------|---------------|
| `problem_state` | `problem.state` (via problem_id reference) | `1` |
| `problem_state_display` | `problem.state` (display value) | `Open` |

### Updated Response

```json
"related_records": {
    "parent_incident": "",
    "problem_id": "03ac7d7d878c62d0d7a676e9cebb356f",
    "problem_id_display": "PRB0015676",
    "problem_state": "1",
    "problem_state_display": "Open",
    "rfc": "",
    "u_fix_change": "",
    "u_jira_number": "OPOS-1087"
}
```

### Why

The intelligence system recommends which Problem record to tag new incidents to. Engineers cannot tag incidents to closed/cancelled problems — they need to know the problem's current state to act on the recommendation. Without this field, we have to make a separate API call per problem to check its state.

### Implementation

This is a single dot-walk from the incident's `problem_id` field to `problem.state`. No additional queries or tables needed — ServiceNow resolves this automatically via the reference field.
