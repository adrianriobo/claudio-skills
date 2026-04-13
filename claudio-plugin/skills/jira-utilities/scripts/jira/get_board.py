#!/usr/bin/env python3
"""Discover Jira Software boards for a given project key.

Wraps GET /rest/agile/1.0/board?projectKeyOrId=<key> with optional
name and type filtering. Pages through all results automatically.

Exit Codes:
    0: Success
    1: Invalid parameters
    2: API error
    3: Not found
    4: Authentication error
"""

import argparse
import json
import sys
from typing import Optional

from client import JiraClient

VALID_BOARD_TYPES = ("scrum", "kanban")


def get_boards(
    project: str,
    name_filter: Optional[str] = None,
    board_type: Optional[str] = None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    auth_type: Optional[str] = None,
) -> list:
    """Discover Jira Software boards for a project.

    Args:
        project: Jira project key (e.g., "MYPROJ")
        name_filter: Case-insensitive substring to filter board names
        board_type: Board type filter: "scrum" or "kanban"
        base_url: Jira instance URL (or from env JIRA_BASE_URL)
        token: Jira API token (or from env JIRA_TOKEN)
        email: User email for Cloud auth (or from env JIRA_EMAIL)
        auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE)

    Returns:
        List of board dicts with id, name, type

    Raises:
        ValueError: If parameters are invalid or credentials missing
        LookupError: If board is not found (404)
        RuntimeError: If API call fails
    """
    if not project:
        raise ValueError("Project key cannot be empty")
    if board_type and board_type not in VALID_BOARD_TYPES:
        raise ValueError(
            f"Invalid board_type {board_type!r}. Must be one of: {', '.join(VALID_BOARD_TYPES)}"
        )

    client = JiraClient(base_url=base_url, token=token, email=email, auth_type=auth_type)
    print(f"Discovering boards for project {project!r}...", file=sys.stderr)

    # Page through all results (capped to avoid unbounded API calls)
    _MAX_PAGES = 20
    boards = []
    start_at = 0
    page_size = 50
    page_count = 0

    while page_count < _MAX_PAGES:
        result = client.get(
            "/rest/agile/1.0/board",
            params={
                "projectKeyOrId": project,
                "startAt": start_at,
                "maxResults": page_size,
            },
        )
        page = result.get("values", [])
        boards.extend(page)
        page_count += 1

        if result.get("isLast", True) or len(page) < page_size:
            break
        start_at += len(page)

    if page_count == _MAX_PAGES:
        print(
            f"WARNING: board listing capped at {_MAX_PAGES * page_size} results",
            file=sys.stderr,
        )

    print(f"Found {len(boards)} board(s) before filtering", file=sys.stderr)

    # Apply filters
    if name_filter:
        boards = [b for b in boards if name_filter.lower() in b.get("name", "").lower()]
    if board_type:
        boards = [b for b in boards if b.get("type", "").lower() == board_type.lower()]

    return [{"id": b["id"], "name": b["name"], "type": b["type"]} for b in boards]


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Discover Jira Software boards for a project"
    )
    parser.add_argument("project", help="Jira project key (e.g., MYPROJ)")
    parser.add_argument(
        "--name",
        dest="name_filter",
        help="Filter boards whose name contains this string (case-insensitive)",
    )
    parser.add_argument(
        "--type",
        dest="board_type",
        choices=list(VALID_BOARD_TYPES),
        help="Filter by board type: scrum or kanban",
    )
    parser.add_argument(
        "--first",
        action="store_true",
        help="Return only the first match as a single JSON object",
    )
    args = parser.parse_args()

    try:
        boards = get_boards(
            project=args.project,
            name_filter=args.name_filter,
            board_type=args.board_type,
        )
        if not boards:
            print(f"ERROR: No boards found for project {args.project!r}", file=sys.stderr)
            return 3

        if args.first:
            print(json.dumps(boards[0]))
        else:
            print(json.dumps(boards))
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
