#!/usr/bin/env python3
"""Link two Jira issues together.

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

VALID_LINK_TYPES = [
    "blocks",
    "is blocked by",
    "clones",
    "is cloned by",
    "duplicates",
    "is duplicated by",
    "relates to",
]


def link_issues(
    inward_key: str,
    outward_key: str,
    link_type: str = "relates to",
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    auth_type: Optional[str] = None,
) -> dict:
    """Link two Jira issues together.

    Args:
        inward_key: Source issue key (e.g., "PROJ-123")
        outward_key: Target issue key (e.g., "PROJ-456")
        link_type: Relationship type (default: "relates to")
                   Common values: "blocks", "is blocked by", "duplicates",
                   "is duplicated by", "relates to", "clones", "is cloned by"
        base_url: Jira instance URL (or from env JIRA_BASE_URL)
        token: Jira API token (or from env JIRA_TOKEN)
        email: User email for Cloud auth (or from env JIRA_EMAIL)
        auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE)

    Returns:
        Empty dict on success (Jira returns 201 No Content)

    Raises:
        ValueError: If issue keys are missing or credentials are invalid
        LookupError: If either issue is not found
        RuntimeError: If API call fails
    """
    if not inward_key or not outward_key:
        raise ValueError("Both inward_key and outward_key must be provided")
    _validate_issue_key(inward_key)
    _validate_issue_key(outward_key)
    if link_type not in VALID_LINK_TYPES:
        raise ValueError(
            f"Invalid link_type {link_type!r}. Must be one of: {', '.join(VALID_LINK_TYPES)}"
        )

    client = JiraClient(base_url=base_url, token=token, email=email, auth_type=auth_type)
    print(
        f"Linking {inward_key} -> {outward_key} ({link_type!r})...",
        file=sys.stderr,
    )

    payload = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_key},
        "outwardIssue": {"key": outward_key},
    }
    result = client.post("/rest/api/3/issueLink", json=payload)
    print(f"Linked {inward_key} and {outward_key}", file=sys.stderr)
    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Link two Jira issues")
    parser.add_argument("inward_key", help="Source issue key (e.g., PROJ-123)")
    parser.add_argument("outward_key", help="Target issue key (e.g., PROJ-456)")
    parser.add_argument(
        "--link-type",
        default="relates to",
        help='Link type (default: "relates to"). '
             'Options: blocks, "is blocked by", duplicates, "is duplicated by", '
             '"relates to", clones, "is cloned by"',
    )
    args = parser.parse_args()

    try:
        link_issues(
            inward_key=args.inward_key,
            outward_key=args.outward_key,
            link_type=args.link_type,
        )
        print(json.dumps({"linked": [args.inward_key, args.outward_key], "type": args.link_type}))
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
