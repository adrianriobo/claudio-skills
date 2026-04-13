---
name: jira-utilities
description: Jira utilities for reading issues, searching with JQL, creating issues, updating fields, linking issues, and fetching sprint information using the Jira REST API. Use this skill when the user asks about Jira issues (e.g. "show my open tickets", "get cards assigned to me", "create a Jira issue", "find bugs in project X") or when another skill needs to interact with Jira. Supports both Jira Cloud (Basic auth) and Jira Data Center (Bearer token / PAT).
compatibility: Requires JIRA_BASE_URL, JIRA_TOKEN, and JIRA_EMAIL (Cloud only) environment variables
allowed-tools: Bash(*/jira-utilities/scripts/jira/*.py:*),Bash(pip3 install -r */jira-utilities/requirements.txt:*)
---

# Jira Utilities

Generic helper utilities for common Jira operations via the Jira REST API v3.

## Why Python REST API (not a CLI)?

Unlike GitLab (`glab`) and AWS (`aws-cli`), **Atlassian does not publish an official first-party CLI for Jira**. All available CLI tools (go-jira, jira-cli, etc.) are community-maintained — they can go unmaintained, have incomplete feature coverage, and introduce unstable flag interfaces.

The Jira REST API is the **authoritative, versioned interface** maintained directly by Atlassian. Using Python `requests` against it is therefore the most official and stable integration path available:

| Criterion | Python REST API | Community CLIs |
|-----------|----------------|---------------|
| Official | Yes — REST API is first-party | No — third-party tools |
| Maintenance | Atlassian-owned, versioned | Community, can be abandoned |
| Feature coverage | Complete | Subset of API |
| Auth flexibility | Full control (Cloud + DC) | Varies by tool |
| Stability | Explicit API versioning (v3+) | CLI flags can change silently |

This is the same pattern used by `slack-utilities`, which also uses direct API calls for the same reason.

## Overview

This skill provides standalone scripts for Jira operations:
- **Get issue** - Fetch a single issue by key
- **Search issues** - Query issues with JQL
- **Create issue** - Create a new issue with full field support
- **Update issue** - Update fields on an existing issue
- **Link issues** - Create relationships between issues
- **Get board** - Discover board IDs for a project key
- **Get sprint** - Fetch sprint info from a Jira Software board (by board ID or project key)

## Prerequisites

**Required environment variables:**
- `JIRA_BASE_URL` - Jira instance URL (e.g., `https://yourorg.atlassian.net`)
- `JIRA_TOKEN` - API token (Cloud) or Personal Access Token (Data Center)
- `JIRA_EMAIL` - User email address (Cloud auth only)
- `JIRA_AUTH_TYPE` - `cloud` or `datacenter` (default: `cloud`)

**Python dependencies:**
```bash
pip3 install -r requirements.txt
```

## Auth Modes

**Jira Cloud** (default, `JIRA_AUTH_TYPE=cloud`):
- Uses HTTP Basic auth: `JIRA_EMAIL:JIRA_TOKEN`
- Token generated at: Atlassian account settings -> Security -> API tokens

**Jira Data Center / Server** (`JIRA_AUTH_TYPE=datacenter`):
- Uses Bearer token auth: `Authorization: Bearer <JIRA_TOKEN>`
- Token is a Personal Access Token (PAT) from Jira user profile

## Scripts

### Get Issue

**Script:** `scripts/jira/get_issue.py`

**Purpose:** Fetch a single Jira issue by key.

**Usage:**
```bash
./scripts/jira/get_issue.py <issue_key>
```

**Example:**
```bash
./scripts/jira/get_issue.py PROJ-123
```

**Output:** Full issue JSON from Jira REST API.

**Exit codes:**
- 0 = success
- 1 = invalid parameters
- 2 = API error
- 3 = not found
- 4 = auth error

---

### Search Issues

**Script:** `scripts/jira/search_issues.py`

**Purpose:** Search Jira issues using JQL (Jira Query Language) or a plain keyword.

**Usage:**
```bash
./scripts/jira/search_issues.py <jql> [--max-results N] [--fields FIELDS]
./scripts/jira/search_issues.py --search KEYWORD [--project KEY] [--max-results N]
```

**Parameters:**
- `jql` - JQL query string (mutually exclusive with `--search` / `--epic`)
- `--search` - Plain keyword to search across all text fields; builds `text ~ "KEYWORD"` JQL automatically
- `--project` - Restrict `--search` to a specific project key (e.g., `MYPROJ`); ignored when using raw JQL
- `--epic` - Fetch all child issues of an Epic key (e.g., `PROJ-42`); expands to `"Epic Link" = KEY OR parent = KEY`, covering both classic and next-gen project types
- `--max-results` - Maximum results to return (default: 50)
- `--fields` - Comma-separated field names to include (default: summary, status, assignee, priority, labels, issuetype, created, updated, description, parent)
- `--format` - Output format: `json` (default, machine-readable) or `table` (human-readable)

**Examples:**
```bash
# Open issues in a project
./scripts/jira/search_issues.py 'project = PROJ AND status = "Open"'

# High priority issues assigned to me
./scripts/jira/search_issues.py 'assignee = currentUser() AND priority = High'

# Issues updated in the last week
./scripts/jira/search_issues.py 'project = PROJ AND updated >= -7d' --max-results 100

# Only fetch key, summary, and status
./scripts/jira/search_issues.py 'project = PROJ' --fields 'summary,status'

# Plain keyword search across all text fields
./scripts/jira/search_issues.py --search "my feature"

# Keyword search scoped to a project
./scripts/jira/search_issues.py --search "my feature" --project MYPROJ

# All child issues of an Epic (works on classic and next-gen projects)
./scripts/jira/search_issues.py --epic PROJ-42

# Human-readable table output
./scripts/jira/search_issues.py --epic PROJ-42 --format table

# Table output for a keyword search
./scripts/jira/search_issues.py --search "my-component" --project MYPROJ --format table
```

**Output:** JSON array of issue objects.

**Exit codes:** same as get_issue

---

### Create Issue

**Script:** `scripts/jira/create_issue.py`

**Purpose:** Create a new Jira issue.

**Usage:**
```bash
./scripts/jira/create_issue.py <project> <summary> [options]
```

**Parameters:**
- `project` - Jira project key (e.g., `PROJ`)
- `summary` - Issue title/summary
- `--description` - Issue description (plain text)
- `--issuetype` - Issue type name (default: `Task`)
- `--priority` - Priority name (optional; omit to use the project default)
- `--labels` - Comma-separated labels
- `--assignee` - Assignee account ID (Jira Cloud) or username (Data Center).
  To find your account ID: `get_issue.py <ANY-KEY> | python3 -m json.tool | grep accountId`
- `--component` - Comma-separated component names (e.g., `My Team`)
- `--team` - Team ID for `customfield_10001` (Atlassian team field). Must be the team's
  UUID string, **not** the display name. Retrieve it from an existing issue:
  `get_issue.py <KEY> | python3 -c "import sys,json; print(json.load(sys.stdin)['fields']['customfield_10001']['id'])"`
- `--epic` - Epic issue key to create this issue under (e.g., `PROJ-42`). Tries the
  modern `parent` field first; automatically falls back to the classic `customfield_10014`
  (Epic Link) if the project does not support it.
- `--activity-type` - Activity Type (`customfield_10464`). Allowed values:
  `Tech Debt & Quality`, `New Features`, `Learning & Enablement`

**Notes:**
- The `--priority` flag is optional. Omit it to let Jira use the project default, avoiding
  "invalid priority" errors across projects with different priority schemes. List valid
  priorities: `curl -u $JIRA_EMAIL:$JIRA_TOKEN "$JIRA_BASE_URL/rest/api/3/priority" | python3 -m json.tool`

**Examples:**
```bash
# Create a basic task
./scripts/jira/create_issue.py PROJ "Fix login timeout"

# Create a bug with full details
./scripts/jira/create_issue.py PROJ "Login fails after 5 minutes" \
  --issuetype Bug \
  --priority High \
  --description "Users report session expiry errors after 5 minutes of inactivity." \
  --labels "backend,auth"

# Create a child task under an epic, assigned to a user, with team and activity type
./scripts/jira/create_issue.py PROJ "Implement login page" \
  --epic PROJ-42 \
  --team "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --assignee "712020:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --component "My Team" \
  --activity-type "New Features"
```

**Output:**
```json
{"id": "10042", "key": "PROJ-42", "self": "https://..."}
```

**Exit codes:** same as get_issue

---

### Update Issue

**Script:** `scripts/jira/update_issue.py`

**Purpose:** Update one or more fields on an existing Jira issue. Only provided fields are changed.

**Usage:**
```bash
./scripts/jira/update_issue.py <issue_key> [options]
```

**Parameters:**
- `issue_key` - Jira issue key (e.g., `PROJ-123`)
- `--summary` - New summary
- `--description` - New description
- `--priority` - New priority (e.g., `Critical`, `High`, `Medium`, `Low`)
- `--assignee` - New assignee username or account ID
- `--labels` - Comma-separated labels (replaces existing labels)

**Examples:**
```bash
# Escalate priority
./scripts/jira/update_issue.py PROJ-123 --priority Critical

# Update summary and add labels
./scripts/jira/update_issue.py PROJ-123 \
  --summary "Fix login timeout (production blocker)" \
  --labels "backend,auth,blocker"
```

**Output:**
```json
{"updated": "PROJ-123"}
```

**Exit codes:** same as get_issue

---

### Link Issues

**Script:** `scripts/jira/link_issues.py`

**Purpose:** Create a relationship link between two Jira issues.

**Usage:**
```bash
./scripts/jira/link_issues.py <inward_key> <outward_key> [--link-type TYPE]
```

**Parameters:**
- `inward_key` - Source issue key
- `outward_key` - Target issue key
- `--link-type` - Relationship type (default: `relates to`)

**Common link types:**
- `blocks` / `is blocked by`
- `duplicates` / `is duplicated by`
- `relates to`
- `clones` / `is cloned by`

**Examples:**
```bash
# Mark as blocker
./scripts/jira/link_issues.py PROJ-123 PROJ-456 --link-type blocks

# Mark as duplicate
./scripts/jira/link_issues.py PROJ-789 PROJ-123 --link-type duplicates
```

**Output:**
```json
{"linked": ["PROJ-123", "PROJ-456"], "type": "blocks"}
```

**Exit codes:** same as get_issue

---

### Get Board

**Script:** `scripts/jira/get_board.py`

**Purpose:** Discover Jira Software boards for a given project key. Use this when the board ID is unknown.

**Usage:**
```bash
./scripts/jira/get_board.py <project> [--name SUBSTRING] [--type TYPE] [--first]
```

**Parameters:**
- `project` - Jira project key (e.g., `MYPROJ`)
- `--name` - Filter boards whose name contains this string (case-insensitive)
- `--type` - Filter by board type: `scrum` or `kanban`
- `--first` - Return only the first match as a single JSON object (not an array)

**Examples:**
```bash
# List all boards for a project
./scripts/jira/get_board.py MYPROJ

# Filter by name substring
./scripts/jira/get_board.py MYPROJ --name "My Team"

# Filter by type and return first match
./scripts/jira/get_board.py MYPROJ --name "My Team" --type scrum --first
```

**Output:**
```json
[
  {
    "id": 42,
    "name": "My Team Board",
    "type": "scrum"
  }
]
```

With `--first`, outputs a single object instead of an array.

**Exit codes:** same as get_issue (exit 3 when no boards match)

---

### Get Sprint

**Script:** `scripts/jira/get_sprint.py`

**Purpose:** Fetch sprint information from a Jira Software board. Requires Jira Software license. Accepts either an explicit board ID or a project key (with automatic board discovery).

**Usage:**
```bash
# By board ID (original usage)
./scripts/jira/get_sprint.py <board_id> [--state STATE]

# By project key (board discovery)
./scripts/jira/get_sprint.py --project KEY [--board-name NAME] [--board-type TYPE] [--state STATE]
```

**Parameters:**
- `board_id` - Jira Software board ID (optional if `--project` is given)
- `--project` - Project key — triggers board discovery (e.g., `MYPROJ`)
- `--board-name` - Name substring filter used during discovery (default: none)
- `--board-type` - Board type filter used during discovery: `scrum` or `kanban` (default: `scrum`)
- `--state` - Sprint state: `active`, `future`, or `closed` (default: `active`)

**Board discovery behaviour** (when `--project` is used):
1. Calls `GET /rest/agile/1.0/board?projectKeyOrId=<key>` and applies `--board-name` / `--board-type` filters.
2. Exactly one match → uses its ID automatically.
3. Zero matches → exit 3 with a descriptive error.
4. Multiple matches → exit 1 and lists matching boards so you can re-run with `--board-name` to disambiguate.

**Examples:**
```bash
# Get active sprint by board ID
./scripts/jira/get_sprint.py 42

# Get upcoming sprints by board ID
./scripts/jira/get_sprint.py 42 --state future

# Get active sprint by project key (board discovery)
./scripts/jira/get_sprint.py --project MYPROJ --state active

# Disambiguate when a project has multiple boards
./scripts/jira/get_sprint.py --project MYPROJ --board-name "My Team" --state active
```

**Output:** JSON array of sprint objects with `id`, `name`, `state`, `startDate`, `endDate`, `goal`.

**Exit codes:** same as get_issue; exit 1 also used when board discovery is ambiguous

---

### CVE Tracker

**Script:** `scripts/jira/cve_tracker.py`

**Purpose:** Query Vulnerability-type issues from a Jira project, deduplicate across
variants (e.g., per-architecture or per-component duplicates of the same CVE), group by
fix version or due-date cluster, and produce a release estimate summary.

**Usage:**
```bash
./scripts/jira/cve_tracker.py <project> [options]
```

**Parameters:**

| Flag | Description |
|------|-------------|
| `project` | Jira project key to query (e.g. `VULN`) |
| `--filter SUBSTR` | Case-insensitive substring filter on issue summary |
| `--issue-type TYPE` | Issue type to query (default: `Vulnerability`) |
| `--status {open,all}` | `open` excludes Closed issues (default); `all` includes all |
| `--cluster-days N` | Window in days for grouping unassigned issues by due date (default: 14) |
| `--format {table,json}` | Output format (default: `table`) |
| `--verbose` | Show individual CVE IDs per group |

**Examples:**
```bash
# Summary table of all open vulnerabilities in project VULN
./scripts/jira/cve_tracker.py VULN

# Filter by component name substring
./scripts/jira/cve_tracker.py VULN --filter mycomponent

# Include closed issues, JSON output
./scripts/jira/cve_tracker.py VULN --status all --format json

# Verbose: show CVE IDs per group
./scripts/jira/cve_tracker.py VULN --verbose

# Tighter clustering window (7-day buckets instead of 14)
./scripts/jira/cve_tracker.py VULN --cluster-days 7
```

**Output (table):**
```
Fix Version / Cluster         CVEs  Issues  Earliest Due  Latest Due    Statuses
──────────────────────────────────────────────────────────────────────────────────────
some-fix-version-1.0             4       7    2026-04-09    2026-04-15  4 Review, 2 Backlog, 1 New
Unassigned ~2026-04             10      27    2026-04-02    2026-04-14  12 Review, 10 New
some-fix-version-0.9 (overdue)   2       4    2026-01-08    2026-01-08  4 Review
```

**Notes:**
- CVE IDs are extracted from issue summaries via `CVE-YYYY-NNNNN` pattern. Issues with
  no matching CVE ID are grouped as `UNKNOWN`.
- One CVE may produce multiple Jira issues (e.g., one per image variant). The script
  deduplicates by CVE ID; `CVEs` counts distinct CVE IDs, `Issues` counts raw Jira issues.
- Groups marked `(overdue)` have a latest due date before today.
- Unassigned clusters are labelled by their earliest due date month.

**Exit codes:** same as all other scripts (0 success, 1 params, 2 API, 3 not found, 4 auth).

---

## Integration with Other Skills

This skill is designed to be imported by other skills:

```python
import sys
sys.path.append('/path/to/jira-utilities/scripts')
from jira.client import JiraClient
from jira.create_issue import create_issue
from jira.search_issues import search_issues
```

Or called as standalone scripts:
```bash
# From dev-triager skill
/path/to/jira-utilities/scripts/jira/create_issue.py PROJ "Card from Slack thread" \
  --description "Context: ..." \
  --priority High \
  --labels "from-slack"
```

## Common Workflows

### Create Card from Slack Thread

```bash
# Create the issue
RESULT=$(./scripts/jira/create_issue.py PROJ "Fix intermittent auth failures" \
  --issuetype Bug \
  --priority High \
  --description "Reported in #team-incidents. Users seeing 401s on login after token refresh." \
  --labels "auth,backend,from-slack")

# Extract the key
KEY=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
echo "Created: $KEY"
```

### Escalate Blocked Issues

```bash
# Find open issues with blocker label
./scripts/jira/search_issues.py 'project = PROJ AND labels = "blocker" AND status != Done' \
  --fields 'summary,priority,status' | \
  python3 -c "import sys,json; [print(i['key'], i['fields']['priority']['name']) for i in json.load(sys.stdin)]"

# Escalate each to Critical
./scripts/jira/update_issue.py PROJ-123 --priority Critical
```

### Find Issues for Planning

```bash
# Issues not in any sprint, high priority
./scripts/jira/search_issues.py \
  'project = PROJ AND sprint is EMPTY AND priority in (High, Critical) AND status != Done' \
  --max-results 20

# Check active sprint end date (board ID known)
./scripts/jira/get_sprint.py 42 | \
  python3 -c "import sys,json; s=json.load(sys.stdin); print(s[0]['endDate'] if s else 'no active sprint')"
```

### Get Active Sprint Without Knowing the Board ID

```bash
# Discover all boards for a project
./scripts/jira/get_board.py MYPROJ

# Narrow down to a specific team board and get active sprint in one step
./scripts/jira/get_sprint.py --project MYPROJ --board-name "My Team" --state active

# Extract sprint end date
./scripts/jira/get_sprint.py --project MYPROJ --board-name "My Team" | \
  python3 -c "import sys,json; s=json.load(sys.stdin); print(s[0]['endDate'] if s else 'no active sprint')"
```

## Testing

Run the test suite:
```bash
pip3 install -r requirements-test.txt
pytest -v
```

Tests use `unittest.mock` to mock all HTTP calls — no real Jira instance required.

## Troubleshooting

**Authentication errors (exit code 4):**
- Cloud: verify `JIRA_EMAIL` and `JIRA_TOKEN` (API token, not account password)
- Data Center: verify `JIRA_TOKEN` is a valid PAT and `JIRA_AUTH_TYPE=datacenter`
- Check token expiry

**Not found errors (exit code 3):**
- Verify issue key format matches your project (e.g., `PROJ-123`)
- Confirm the project key is correct
- Check user has read permissions on the project

**API errors (exit code 2):**
- Check network connectivity to `JIRA_BASE_URL`
- Verify the base URL does not include a trailing path (e.g., use `https://yourorg.atlassian.net`, not `https://yourorg.atlassian.net/jira`)
- For `get_sprint`: confirm the instance has Jira Software license

**Field validation errors on create/update:**
- Issue type names are case-sensitive and must match your project's configured types
- Priority names must match the instance's priority scheme
- Labels cannot contain spaces
