#!/usr/bin/env python3
"""Fetch a Jira issue by key.

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

from client import JiraClient

_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def _validate_issue_key(key: str) -> None:
    if not _ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid issue key format: {key!r} (expected e.g. PROJ-123)")


def get_issue(
    issue_key: str,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    auth_type: Optional[str] = None,
) -> dict:
    """Fetch a Jira issue by key.

    Args:
        issue_key: Jira issue key (e.g., "PROJ-123")
        base_url: Jira instance URL (or from env JIRA_BASE_URL)
        token: Jira API token (or from env JIRA_TOKEN)
        email: User email for Cloud auth (or from env JIRA_EMAIL)
        auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE)

    Returns:
        Issue dict with key, summary, status, assignee, priority, etc.

    Raises:
        ValueError: If credentials are missing or invalid
        LookupError: If issue is not found
        RuntimeError: If API call fails
    """
    _validate_issue_key(issue_key)
    client = JiraClient(base_url=base_url, token=token, email=email, auth_type=auth_type)
    print(f"Fetching issue {issue_key}...", file=sys.stderr)
    issue = client.get(f"/rest/api/3/issue/{issue_key}")
    print(f"Fetched issue {issue_key}", file=sys.stderr)
    return issue


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fetch a Jira issue by key")
    parser.add_argument("issue_key", help="Jira issue key (e.g., PROJ-123)")
    args = parser.parse_args()

    try:
        issue = get_issue(args.issue_key)
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
