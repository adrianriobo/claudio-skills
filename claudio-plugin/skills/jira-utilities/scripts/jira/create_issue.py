#!/usr/bin/env python3
"""Create a Jira issue.

Exit Codes:
    0: Success
    1: Invalid parameters
    2: API error
    3: Not found
    4: Authentication error
"""

import argparse
import json
import re
import sys
from typing import Optional

from client import JiraClient, to_adf

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

ACTIVITY_TYPES = ("Tech Debt & Quality", "New Features", "Learning & Enablement")


def _validate_activity_type(value: str) -> None:
    if value not in ACTIVITY_TYPES:
        raise ValueError(
            f"Invalid activity_type {value!r}. Must be one of: {', '.join(ACTIVITY_TYPES)}"
        )


def create_issue(
    project: str,
    summary: str,
    description: str = "",
    issuetype: str = "Task",
    priority: Optional[str] = None,
    labels: Optional[list] = None,
    assignee: Optional[str] = None,
    components: Optional[list] = None,
    team: Optional[str] = None,
    epic: Optional[str] = None,
    activity_type: Optional[str] = None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    auth_type: Optional[str] = None,
) -> dict:
    """Create a Jira issue.

    Args:
        project: Jira project key (e.g., "PROJ")
        summary: Issue title/summary
        description: Issue description (plain text)
        issuetype: Issue type name (default: "Task")
        priority: Priority name (optional; omit to use the project default)
        labels: List of label strings
        assignee: Assignee account ID (Cloud) or username (Data Center)
        components: List of component name strings (e.g., ["My Team"])
        team: Team ID for customfield_10001 (Atlassian team field). Must be the
              team's UUID string, not the display name. Retrieve from an existing
              issue: get_issue.py <KEY> | python3 -c
              "import sys,json; print(json.load(sys.stdin)['fields']['customfield_10001']['id'])"
        epic: Epic issue key to link this issue under (e.g., "PROJ-42").
              Tries the modern `parent` field first; falls back to the classic
              `customfield_10014` (Epic Link) if the project does not support it.
        activity_type: Activity Type value (customfield_10464). One of:
            "Tech Debt & Quality", "New Features", "Learning & Enablement"
        base_url: Jira instance URL (or from env JIRA_BASE_URL)
        token: Jira API token (or from env JIRA_TOKEN)
        email: User email for Cloud auth (or from env JIRA_EMAIL)
        auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE)

    Returns:
        Created issue dict with id, key, and self URL

    Raises:
        ValueError: If required fields are missing or credentials are invalid
        RuntimeError: If API call fails
    """
    if not project:
        raise ValueError("Project key cannot be empty")
    if not summary:
        raise ValueError("Summary cannot be empty")
    if len(summary) > 255:
        raise ValueError(f"Summary exceeds 255 characters ({len(summary)})")
    if description and len(description) > 32_767:
        raise ValueError(f"Description exceeds 32,767 characters ({len(description)})")
    if team and not _UUID_RE.match(team):
        raise ValueError(f"--team must be a UUID string, got: {team!r}")

    client = JiraClient(base_url=base_url, token=token, email=email, auth_type=auth_type)

    fields = {
        "project": {"key": project},
        "summary": summary,
        "issuetype": {"name": issuetype},
    }

    if priority:
        fields["priority"] = {"name": priority}

    if description:
        fields["description"] = to_adf(description)

    if labels:
        fields["labels"] = labels

    if assignee:
        # Jira Cloud uses accountId; Data Center uses name.
        key = "name" if (auth_type or "cloud") == "datacenter" else "accountId"
        fields["assignee"] = {key: assignee}

    if components:
        fields["components"] = [{"name": c} for c in components]

    if team:
        # customfield_10001 is the Atlassian team field. The API requires the
        # team ID as a plain string (not wrapped in an object).
        fields["customfield_10001"] = team

    if activity_type:
        _validate_activity_type(activity_type)
        fields["customfield_10464"] = {"value": activity_type}

    print(f"Creating {issuetype} in {project}: {summary!r}...", file=sys.stderr)

    if epic:
        result = _create_with_epic(client, fields, epic)
    else:
        result = client.post("/rest/api/3/issue", json={"fields": fields})

    print(f"Created issue {result.get('key', 'unknown')}", file=sys.stderr)
    return result


def _create_with_epic(client: JiraClient, fields: dict, epic: str) -> dict:
    """Create an issue linked to an epic, trying `parent` then falling back to
    the classic `customfield_10014` (Epic Link) for older project types.

    Args:
        client: Authenticated JiraClient instance
        fields: Issue fields dict (mutated in place per attempt)
        epic: Epic issue key (e.g., "PROJ-42")

    Returns:
        Created issue dict with id, key, and self URL
    """
    # Modern next-gen / team-managed projects use the standard `parent` field.
    fields["parent"] = {"key": epic}
    try:
        return client.post("/rest/api/3/issue", json={"fields": fields})
    except RuntimeError as exc:
        error_str = str(exc).lower()
        # Jira returns a field error when `parent` is not supported.
        if "parent" not in error_str and "field" not in error_str:
            raise

    # Fall back to the classic Epic Link custom field used by company-managed
    # (formerly "classic") projects.
    print(
        "Note: 'parent' field not accepted; retrying with customfield_10014 (Epic Link).",
        file=sys.stderr,
    )
    del fields["parent"]
    fields["customfield_10014"] = epic
    return client.post("/rest/api/3/issue", json={"fields": fields})


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create a Jira issue")
    parser.add_argument("project", help="Jira project key (e.g., PROJ)")
    parser.add_argument("summary", help="Issue summary/title")
    parser.add_argument("--description", default="", help="Issue description")
    parser.add_argument("--issuetype", default="Task", help="Issue type (default: Task)")
    parser.add_argument("--priority", default=None, help="Priority name")
    parser.add_argument("--labels", help="Comma-separated labels")
    parser.add_argument("--assignee", help="Assignee account ID (Cloud) or username (Data Center)")
    parser.add_argument("--component", help="Comma-separated component names (e.g., 'My Team')")
    parser.add_argument("--team", help="Team ID for customfield_10001 (UUID string, not display name)")
    parser.add_argument("--epic", help="Epic issue key to link this issue under (e.g., PROJ-42)")
    parser.add_argument(
        "--activity-type",
        dest="activity_type",
        choices=ACTIVITY_TYPES,
        help="Activity Type: 'Tech Debt & Quality', 'New Features', or 'Learning & Enablement'",
    )
    args = parser.parse_args()

    labels = [l.strip() for l in args.labels.split(",")] if args.labels else None
    components = [c.strip() for c in args.component.split(",")] if args.component else None

    try:
        issue = create_issue(
            project=args.project,
            summary=args.summary,
            description=args.description,
            issuetype=args.issuetype,
            priority=args.priority,
            labels=labels,
            assignee=args.assignee,
            components=components,
            team=args.team,
            epic=args.epic,
            activity_type=args.activity_type,
        )
        print(json.dumps(issue))
        return 0
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4 if "auth" in str(e).lower() or "token" in str(e).lower() or "email" in str(e).lower() else 1
    except LookupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
