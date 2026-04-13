#!/usr/bin/env python3
"""Search Jira issues using JQL or a plain keyword.

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

DEFAULT_FIELDS = "summary,status,assignee,priority,labels,issuetype,created,updated,description,parent"


def keyword_to_jql(keyword: str, project: Optional[str] = None) -> str:
    """Build a JQL full-text search query from a plain keyword.

    Args:
        keyword: Plain text to search for across all Jira text fields.
        project: Optional project key to restrict the search (e.g., "PROJ").

    Returns:
        JQL string using the `text ~` operator.
    """
    # Escape double-quotes inside the keyword so the JQL stays valid.
    escaped = keyword.replace('"', '\\"')
    jql = f'text ~ "{escaped}"'
    if project:
        jql = f'project = {project} AND {jql}'
    return jql


def epic_to_jql(epic_key: str) -> str:
    """Build a JQL query to find all child issues of an Epic.

    Covers both modern (parent =) and classic (Epic Link =) project types.

    Args:
        epic_key: Epic issue key (e.g., "PROJ-42").

    Returns:
        JQL string matching children via either field.
    """
    return f'"Epic Link" = {epic_key} OR parent = {epic_key}'


def search_issues(
    jql: str,
    max_results: int = 50,
    fields: str = DEFAULT_FIELDS,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    email: Optional[str] = None,
    auth_type: Optional[str] = None,
    verbose: bool = True,
) -> list:
    """Search Jira issues using JQL.

    Args:
        jql: JQL query string (e.g., 'project = PROJ AND status = "In Progress"')
        max_results: Maximum number of results to return (default: 50)
        fields: Comma-separated list of fields to include
        base_url: Jira instance URL (or from env JIRA_BASE_URL)
        token: Jira API token (or from env JIRA_TOKEN)
        email: User email for Cloud auth (or from env JIRA_EMAIL)
        auth_type: "cloud" or "datacenter" (or from env JIRA_AUTH_TYPE)

    Returns:
        List of issue dicts

    Raises:
        ValueError: If credentials are missing or JQL is invalid
        RuntimeError: If API call fails
    """
    if not jql:
        raise ValueError("JQL query cannot be empty")

    client = JiraClient(base_url=base_url, token=token, email=email, auth_type=auth_type)
    if verbose:
        print(f"Searching issues: {jql}", file=sys.stderr)

    fields_list = [f.strip() for f in fields.split(",")] if isinstance(fields, str) else list(fields)
    result = client.post(
        "/rest/api/3/search/jql",
        json={
            "jql": jql,
            "maxResults": max_results,
            "fields": fields_list,
        },
    )

    issues = result.get("issues", [])
    total = result.get("total", len(issues))
    if verbose:
        print(f"Found {len(issues)} issues (total: {total})", file=sys.stderr)
    return issues


def _print_table(issues: list) -> None:
    """Print issues as a human-readable table."""
    header = f"{'Key':<15} {'Type':<12} {'Status':<15} {'Assignee':<30} Summary"
    print(header)
    print("-" * len(header))
    for issue in issues:
        key = issue["key"]
        fields = issue["fields"]
        itype = fields.get("issuetype", {}).get("name", "")
        status = fields.get("status", {}).get("name", "")
        assignee_obj = fields.get("assignee") or {}
        assignee = assignee_obj.get("displayName", "Unassigned")
        summary = fields.get("summary", "")
        print(f"{key:<15} {itype:<12} {status:<15} {assignee:<30} {summary}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Search Jira issues using JQL or a plain keyword",
        epilog=(
            "Examples:\n"
            "  %(prog)s 'project = PROJ AND status = \"Open\"'\n"
            "  %(prog)s --search alice\n"
            "  %(prog)s --search alice --project MYPROJ\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # jql is now optional so --search can be used instead
    parser.add_argument(
        "jql",
        nargs="?",
        help='JQL query (e.g., \'project = PROJ AND status = "Open"\')',
    )
    parser.add_argument(
        "--search",
        metavar="KEYWORD",
        help='Plain keyword to search across all text fields (builds text ~ "KEYWORD" JQL)',
    )
    parser.add_argument(
        "--project",
        metavar="KEY",
        help="Restrict --search to a specific project key (e.g., MYPROJ)",
    )
    parser.add_argument(
        "--epic",
        metavar="KEY",
        help='Fetch all child issues of an Epic key (e.g., PROJ-42); '
             'expands to "Epic Link" = KEY OR parent = KEY',
    )
    parser.add_argument("--max-results", type=int, default=50, help="Maximum results (default: 50)")
    parser.add_argument("--fields", default=DEFAULT_FIELDS, help="Comma-separated fields to include")
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format: json (default) or table",
    )
    args = parser.parse_args()

    inputs = sum([bool(args.jql), bool(args.search), bool(args.epic)])
    if inputs > 1:
        print("ERROR: provide only one of: JQL query, --search, or --epic.", file=sys.stderr)
        return 1
    if inputs == 0:
        print("ERROR: provide a JQL query, --search KEYWORD, or --epic KEY.", file=sys.stderr)
        return 1

    if args.search:
        jql = keyword_to_jql(args.search, project=args.project)
    elif args.epic:
        jql = epic_to_jql(args.epic)
    else:
        jql = args.jql

    try:
        issues = search_issues(jql, max_results=args.max_results, fields=args.fields, verbose=args.format != "json")
        if args.format == "table":
            _print_table(issues)
        else:
            print(json.dumps(issues))
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
