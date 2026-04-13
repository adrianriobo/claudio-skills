#!/usr/bin/env python3
"""Query Vulnerability-type issues from a Jira project, deduplicate by CVE ID,
group by fix version or due-date cluster, and produce a release estimate summary.

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
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from client import JiraClient

CVE_RE = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)

MAX_RESULTS = 500


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse a YYYY-MM-DD date string into a date object, or return None."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _format_date(d: Optional[date]) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


def _jql_escape(s: str) -> str:
    """Escape backslash and double-quote for JQL string literals."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_jql(project: str, issue_type: str, status: str, filter_substr: Optional[str]) -> str:
    """Construct the JQL query from CLI parameters."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,49}", project):
        raise ValueError(f"Invalid project key: {project!r}")
    parts = [
        f'project = "{_jql_escape(project)}"',
        f'issuetype = "{_jql_escape(issue_type)}"',
    ]
    if status == "open":
        parts.append("status != Closed")
    if filter_substr:
        parts.append(f'summary ~ "{_jql_escape(filter_substr)}"')
    return " AND ".join(parts) + " ORDER BY duedate ASC"


def _fetch_issues(jql: str) -> list:
    """Fetch issues via JiraClient and warn if results are truncated."""
    client = JiraClient()
    print(f"Querying: {jql}", file=sys.stderr)
    result = client.post(
        "/rest/api/3/search/jql",
        json={
            "jql": jql,
            "maxResults": MAX_RESULTS,
            "fields": ["summary", "status", "duedate", "fixVersions"],
        },
    )
    issues = result.get("issues", [])
    total = result.get("total", len(issues))
    print(f"Fetched {len(issues)} of {total} issues", file=sys.stderr)
    if total > MAX_RESULTS:
        print(
            f"WARNING: result set truncated at {MAX_RESULTS}; {total - MAX_RESULTS} issues omitted.",
            file=sys.stderr,
        )
    return issues


def _extract_cve_id(summary: str) -> str:
    """Return the first CVE-YYYY-NNNNN found in summary, uppercased, or 'UNKNOWN'."""
    m = CVE_RE.search(summary)
    return m.group(0).upper() if m else "UNKNOWN"


def _deduplicate(issues: list) -> dict:
    """Group issues by CVE ID and compute per-CVE aggregate fields.

    Returns a dict mapping cve_id -> {
        'due_date': date | None,
        'issue_keys': [str],
        'statuses': Counter,
        'fix_version': str | None,
    }
    """
    groups: dict = {}
    for issue in issues:
        key = issue["key"]
        fields = issue["fields"]
        summary = fields.get("summary", "")
        cve_id = _extract_cve_id(summary)

        due_date = _parse_date(fields.get("duedate"))
        status_name = (fields.get("status") or {}).get("name", "Unknown")
        fix_versions = fields.get("fixVersions") or []
        fix_version = fix_versions[0]["name"] if fix_versions else None

        if cve_id not in groups:
            groups[cve_id] = {
                "due_date": due_date,
                "issue_keys": [key],
                "statuses": Counter([status_name]),
                "fix_version": fix_version,
            }
        else:
            entry = groups[cve_id]
            entry["issue_keys"].append(key)
            entry["statuses"][status_name] += 1
            # Earliest due date wins
            if due_date is not None:
                if entry["due_date"] is None or due_date < entry["due_date"]:
                    entry["due_date"] = due_date
            # First non-None fix version wins
            if entry["fix_version"] is None and fix_version is not None:
                entry["fix_version"] = fix_version
    return groups


def _group_by_fix_version(cve_entries: dict) -> dict:
    """Aggregate assigned CVE entries by fix version name.

    Returns a dict mapping fix_version_name -> {
        'cve_count', 'issue_count', 'earliest_due', 'latest_due', 'statuses', 'cves'
    }
    """
    buckets: dict = {}
    for cve_id, entry in cve_entries.items():
        fv = entry["fix_version"]
        if fv not in buckets:
            buckets[fv] = {
                "cve_count": 0,
                "issue_count": 0,
                "earliest_due": None,
                "latest_due": None,
                "statuses": Counter(),
                "cves": [],
            }
        b = buckets[fv]
        b["cve_count"] += 1
        b["issue_count"] += len(entry["issue_keys"])
        b["statuses"] += entry["statuses"]
        b["cves"].append(cve_id)
        d = entry["due_date"]
        if d is not None:
            if b["earliest_due"] is None or d < b["earliest_due"]:
                b["earliest_due"] = d
            if b["latest_due"] is None or d > b["latest_due"]:
                b["latest_due"] = d
    return buckets


def _cluster_unassigned(cve_entries: dict, cluster_days: int) -> list:
    """Group unassigned CVE entries into due-date clusters.

    Returns a list of group dicts (same shape as fix-version groups), each with
    an additional 'cluster_label' key.
    """
    # Sort by due_date; None goes last
    sorted_entries = sorted(
        cve_entries.items(),
        key=lambda kv: (kv[1]["due_date"] is None, kv[1]["due_date"] or date.max),
    )

    clusters: list = []
    current: Optional[dict] = None
    cluster_start: Optional[date] = None

    for cve_id, entry in sorted_entries:
        d = entry["due_date"]
        # Start a new cluster when gap from cluster start exceeds cluster_days or first entry
        if (
            current is None
            or cluster_start is None
            or d is None
            or (d - cluster_start).days > cluster_days
        ):
            # Label by year-month of earliest due date
            if d is not None:
                label = f"Unassigned ~{d.strftime('%Y-%m')}"
                cluster_start = d
            else:
                label = "Unassigned (no due date)"
                cluster_start = None
            current = {
                "cluster_label": label,
                "cve_count": 0,
                "issue_count": 0,
                "earliest_due": d,
                "latest_due": d,
                "statuses": Counter(),
                "cves": [],
            }
            clusters.append(current)

        current["cve_count"] += 1
        current["issue_count"] += len(entry["issue_keys"])
        current["statuses"] += entry["statuses"]
        current["cves"].append(cve_id)
        if d is not None:
            if current["earliest_due"] is None or d < current["earliest_due"]:
                current["earliest_due"] = d
            if current["latest_due"] is None or d > current["latest_due"]:
                current["latest_due"] = d

    return clusters


def _build_groups(issues: list, cluster_days: int, today: date) -> list:
    """Deduplicate, split, aggregate, and sort all groups.

    Returns a list of group dicts ready for rendering, each containing:
        label, fix_version (or None), cve_count, issue_count,
        earliest_due, latest_due, overdue, statuses, cves
    """
    all_cves = _deduplicate(issues)

    assigned = {cve_id: e for cve_id, e in all_cves.items() if e["fix_version"] is not None}
    unassigned = {cve_id: e for cve_id, e in all_cves.items() if e["fix_version"] is None}

    fv_buckets = _group_by_fix_version(assigned)
    unassigned_clusters = _cluster_unassigned(unassigned, cluster_days)

    groups = []

    for fv_name, b in fv_buckets.items():
        overdue = b["latest_due"] is not None and b["latest_due"] < today
        label = f"{fv_name} (overdue)" if overdue else fv_name
        groups.append({
            "label": label,
            "fix_version": fv_name,
            "cluster_label": label,
            "cve_count": b["cve_count"],
            "issue_count": b["issue_count"],
            "earliest_due": b["earliest_due"],
            "latest_due": b["latest_due"],
            "overdue": overdue,
            "statuses": b["statuses"],
            "cves": sorted(b["cves"]),
        })

    for cluster in unassigned_clusters:
        overdue = cluster["latest_due"] is not None and cluster["latest_due"] < today
        label = cluster["cluster_label"]
        if overdue and "(overdue)" not in label:
            label = f"{label} (overdue)"
        groups.append({
            "label": label,
            "fix_version": None,
            "cluster_label": label,
            "cve_count": cluster["cve_count"],
            "issue_count": cluster["issue_count"],
            "earliest_due": cluster["earliest_due"],
            "latest_due": cluster["latest_due"],
            "overdue": overdue,
            "statuses": cluster["statuses"],
            "cves": sorted(cluster["cves"]),
        })

    # Sort by earliest_due ascending; None sorts last
    groups.sort(key=lambda g: (g["earliest_due"] is None, g["earliest_due"] or date.max))
    return groups


def _format_statuses(statuses: Counter) -> str:
    return ", ".join(f"{count} {name}" for name, count in statuses.most_common())


def _print_table(groups: list, verbose: bool) -> None:
    """Print groups as a human-readable aligned table."""
    col_label = 34
    col_cves = 5
    col_issues = 7
    col_earliest = 13
    col_latest = 13

    header = (
        f"{'Fix Version / Cluster':<{col_label}} "
        f"{'CVEs':>{col_cves}} "
        f"{'Issues':>{col_issues}} "
        f"{'Earliest Due':<{col_earliest}} "
        f"{'Latest Due':<{col_latest}} "
        f"Statuses"
    )
    print(header)
    print("\u2500" * 86)

    for g in groups:
        label = g["label"]
        # Truncate label if too long
        if len(label) > col_label:
            label = label[: col_label - 1] + "\u2026"
        row = (
            f"{label:<{col_label}} "
            f"{g['cve_count']:>{col_cves}} "
            f"{g['issue_count']:>{col_issues}} "
            f"{_format_date(g['earliest_due']):<{col_earliest}} "
            f"{_format_date(g['latest_due']):<{col_latest}} "
            f"{_format_statuses(g['statuses'])}"
        )
        print(row)

        if verbose:
            cves_str = ", ".join(g["cves"])
            print(f"  CVEs: {cves_str}")


def _print_json(groups: list) -> None:
    """Print groups as a JSON array."""
    output = []
    for g in groups:
        output.append({
            "fix_version": g["fix_version"],
            "cluster_label": g["cluster_label"],
            "cve_count": g["cve_count"],
            "issue_count": g["issue_count"],
            "earliest_due": _format_date(g["earliest_due"]) or None,
            "latest_due": _format_date(g["latest_due"]) or None,
            "overdue": g["overdue"],
            "statuses": dict(g["statuses"]),
            "cves": g["cves"],
        })
    print(json.dumps(output, indent=2))


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Query Vulnerability-type issues from a Jira project, deduplicate by CVE ID,\n"
            "group by fix version or due-date cluster, and produce a release estimate summary."
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s VULN\n"
            "  %(prog)s VULN --filter mycomponent\n"
            "  %(prog)s VULN --status all --format json\n"
            "  %(prog)s VULN --verbose\n"
            "  %(prog)s VULN --cluster-days 7\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "project",
        help="Jira project key to query (e.g. VULN)",
    )
    parser.add_argument(
        "--filter",
        metavar="SUBSTR",
        dest="filter_substr",
        default=None,
        help=(
            "Case-insensitive substring filter on issue summary "
            "(useful for narrowing to a specific component or product). "
            "Omit to include all issues in the project."
        ),
    )
    parser.add_argument(
        "--issue-type",
        metavar="TYPE",
        default="Vulnerability",
        help="Issue type to query (default: Vulnerability)",
    )
    parser.add_argument(
        "--status",
        choices=["open", "all"],
        default="open",
        help="open = exclude Closed issues (default); all = include all",
    )
    parser.add_argument(
        "--cluster-days",
        metavar="N",
        type=int,
        default=14,
        help="Window in days for grouping unassigned-version issues by due date (default: 14)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show individual CVE IDs per group",
    )
    args = parser.parse_args()

    if args.cluster_days < 1:
        print("ERROR: --cluster-days must be >= 1", file=sys.stderr)
        return 1

    jql = _build_jql(args.project, args.issue_type, args.status, args.filter_substr)

    try:
        issues = _fetch_issues(jql)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4 if any(w in str(e).lower() for w in ("auth", "token", "email")) else 1
    except LookupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not issues:
        print("No issues found.", file=sys.stderr)
        if args.format == "json":
            print("[]")
        return 0

    today = date.today()
    groups = _build_groups(issues, args.cluster_days, today)

    if args.format == "json":
        _print_json(groups)
    else:
        _print_table(groups, args.verbose)

    return 0


if __name__ == "__main__":
    sys.exit(main())
