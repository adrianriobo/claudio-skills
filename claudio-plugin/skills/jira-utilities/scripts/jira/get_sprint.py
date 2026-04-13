#!/usr/bin/env python3
"""Fetch sprint information from a Jira Software board.

Requires Jira Software (not available on all Jira instances).

Exit Codes:
    0: Success
    1: Invalid parameters / ambiguous board
    2: API error
    3: Not found
    4: Authentication error
"""

import argparse
import json
import sys
from typing import Optional

from client import JiraClient
from get_board import get_boards

VALID_STATES = ("active", "future", "closed")


def get_sprint(
    board_id: int,
    state: str = "active",
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    auth_type: Optional[str] = None,
) -> list:
    """Fetch sprints for a Jira Software board.

    Args:
        board_id: Jira Software board ID
        state: Sprint state filter - "active", "future", or "closed" (default: "active")
        base_url: Jira instance URL (or from env JIRA_BASE_URL)
        token: Jira API token (or from env JIRA_TOKEN)
        email: User email for Cloud auth (or from env JIRA_EMAIL)
        auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE)

    Returns:
        List of sprint dicts with id, name, state, startDate, endDate, goal

    Raises:
        ValueError: If state is invalid or credentials are missing
        LookupError: If board is not found
        RuntimeError: If API call fails
    """
    if state not in VALID_STATES:
        raise ValueError(
            f"Invalid state {state!r}. Must be one of: {', '.join(VALID_STATES)}"
        )

    client = JiraClient(base_url=base_url, token=token, email=email, auth_type=auth_type)
    print(f"Fetching {state} sprints for board {board_id}...", file=sys.stderr)

    result = client.get(
        f"/rest/agile/1.0/board/{board_id}/sprint",
        params={"state": state},
    )

    sprints = result.get("values", [])
    print(f"Found {len(sprints)} {state} sprint(s)", file=sys.stderr)
    return sprints


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch sprint information from a Jira Software board"
    )
    parser.add_argument(
        "board_id",
        type=int,
        nargs="?",
        help="Jira Software board ID (optional if --project is given)",
    )
    parser.add_argument(
        "--project",
        help="Project key — triggers board discovery (e.g., MYPROJ)",
    )
    parser.add_argument(
        "--board-name",
        help="Name substring filter used during board discovery (default: none)",
    )
    parser.add_argument(
        "--board-type",
        default="scrum",
        choices=["scrum", "kanban"],
        help="Board type filter used during board discovery (default: scrum)",
    )
    parser.add_argument(
        "--state",
        default="active",
        choices=list(VALID_STATES),
        help="Sprint state filter (default: active)",
    )
    args = parser.parse_args()

    if args.board_id is None and not args.project:
        print("ERROR: Provide either board_id or --project", file=sys.stderr)
        return 1

    try:
        board_id = args.board_id

        if args.project:
            boards = get_boards(project=args.project, name_filter=args.board_name,
                                board_type=args.board_type)
            if not boards:
                suffix = f" with name containing {args.board_name!r}" if args.board_name else ""
                print(f"ERROR: No boards found for project {args.project!r}{suffix}",
                      file=sys.stderr)
                return 3
            if len(boards) > 1:
                print(
                    f"ERROR: Ambiguous — {len(boards)} boards found for project "
                    f"{args.project!r}. Re-run with --board-name to disambiguate:",
                    file=sys.stderr,
                )
                print(json.dumps(boards, indent=2), file=sys.stderr)
                return 1
            board_id = boards[0]["id"]
            print(f"Resolved board: {boards[0]['name']} (ID: {board_id})", file=sys.stderr)

        sprints = get_sprint(board_id=board_id, state=args.state)
        print(json.dumps(sprints))
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
