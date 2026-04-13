#!/usr/bin/env python3
"""Update a Jira issue's fields.

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

_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def _validate_issue_key(key: str) -> None:
    if not _ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue key format: {key!r} (expected e.g. PROJ-123)")


def update_issue(
    issue_key: str,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    labels: Optional[list] = None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    auth_type: Optional[str] = None,
) -> dict:
    """Update a Jira issue's fields.

    Only provided fields are updated; omitted fields are left unchanged.

    Args:
        issue_key: Jira issue key (e.g., "PROJ-123")
        summary: New summary/title
        description: New description (plain text)
        priority: New priority name (e.g., "High", "Critical")
        assignee: New assignee username or account ID
        labels: New list of labels (replaces existing labels)
        base_url: Jira instance URL (or from env JIRA_BASE_URL)
        token: Jira API token (or from env JIRA_TOKEN)
        email: User email for Cloud auth (or from env JIRA_EMAIL)
        auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE)

    Returns:
        Empty dict on success (Jira returns 204 No Content)

    Raises:
        ValueError: If no fields to update or credentials are invalid
        LookupError: If issue is not found
        RuntimeError: If API call fails
    """
    fields = {}

    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = to_adf(description)
    if priority is not None:
        fields["priority"] = {"name": priority}
    if assignee is not None:
        assignee_key = "name" if (auth_type or "cloud") == "datacenter" else "accountId"
        fields["assignee"] = {assignee_key: assignee}
    if labels is not None:
        fields["labels"] = labels

    if not fields:
        raise ValueError("No fields provided to update")

    _validate_issue_key(issue_key)
    if summary is not None and len(summary) > 255:
        raise ValueError(f"Summary exceeds 255 characters ({len(summary)})")
    if description is not None and len(description) > 32_767:
        raise ValueError(f"Description exceeds 32,767 characters ({len(description)})")

    client = JiraClient(base_url=base_url, token=token, email=email, auth_type=auth_type)
    print(f"Updating issue {issue_key} fields: {list(fields.keys())}...", file=sys.stderr)
    result = client.put(f"/rest/api/3/issue/{issue_key}", json={"fields": fields})
    print(f"Updated issue {issue_key}", file=sys.stderr)
    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Update a Jira issue")
    parser.add_argument("issue_key", help="Jira issue key (e.g., PROJ-123)")
    parser.add_argument("--summary", help="New summary")
    parser.add_argument("--description", help="New description")
    parser.add_argument("--priority", help="New priority (e.g., High, Critical, Medium, Low)")
    parser.add_argument("--assignee", help="New assignee username or account ID")
    parser.add_argument("--labels", help="Comma-separated labels (replaces existing)")
    args = parser.parse_args()

    labels = [l.strip() for l in args.labels.split(",")] if args.labels else None

    try:
        update_issue(
            issue_key=args.issue_key,
            summary=args.summary,
            description=args.description,
            priority=args.priority,
            assignee=args.assignee,
            labels=labels,
        )
        print(json.dumps({"updated": args.issue_key}))
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
