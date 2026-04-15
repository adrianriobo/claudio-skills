#!/usr/bin/env bash
#
# Update fields on an existing Jira issue. Only provided fields are changed.
#
# All fields — including priority which acli does not expose as an edit flag —
# are passed via a single JSON file using acli's --from-json with the
# additionalAttributes key.
#
# Usage:
#   ./update_issue.sh <issue_key> [options]
#
# Options:
#   --summary TEXT      New summary/title
#   --description TEXT  New description
#   --priority NAME     New priority (e.g., Critical, High, Medium, Low)
#   --assignee ID       New assignee account ID or email
#   --labels l1,l2      New labels, comma-separated (replaces existing)
#
# Output: JSON {"updated": "<issue_key>"}
# Exit codes: 0=success, 1=invalid params, 2=API error, 4=auth error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

SUMMARY=""
DESCRIPTION=""
PRIORITY=""
ASSIGNEE=""
LABELS=""

if [[ $# -lt 1 ]]; then
    echo "Usage: $(basename "$0") <issue_key> [options]" >&2
    exit 1
fi

KEY="$1"; shift

if [[ ! "$KEY" =~ ^[A-Z][A-Z0-9_]+-[0-9]+$ ]]; then
    echo "ERROR: Invalid issue key format: '$KEY' (expected e.g. PROJ-123)" >&2
    exit 1
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --summary)     SUMMARY="$2";     shift 2 ;;
        --description) DESCRIPTION="$2"; shift 2 ;;
        --priority)    PRIORITY="$2";    shift 2 ;;
        --assignee)    ASSIGNEE="$2";    shift 2 ;;
        --labels)      LABELS="$2";      shift 2 ;;
        *) echo "ERROR: Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$SUMMARY" && -z "$DESCRIPTION" && -z "$PRIORITY" && -z "$ASSIGNEE" && -z "$LABELS" ]]; then
    echo "ERROR: No fields provided to update." >&2
    exit 1
fi

ensure_auth

# ---- Build JSON payload ----
JSON="{}"

[[ -n "$SUMMARY" ]]     && JSON=$(echo "$JSON" | jq --arg v "$SUMMARY"     '. + {summary: $v}')
[[ -n "$DESCRIPTION" ]] && JSON=$(echo "$JSON" | jq --arg v "$DESCRIPTION" '. + {description: $v}')
[[ -n "$ASSIGNEE" ]]    && JSON=$(echo "$JSON" | jq --arg v "$ASSIGNEE"    '. + {assignee: $v}')

if [[ -n "$LABELS" ]]; then
    LABELS_JSON=$(printf '%s' "$LABELS" | jq -R 'split(",") | map(ltrimstr(" ") | rtrimstr(" ")) | map(select(. != ""))')
    JSON=$(echo "$JSON" | jq --argjson v "$LABELS_JSON" '. + {labels: $v}')
fi

# ---- additionalAttributes for priority (not exposed by acli edit) ----
if [[ -n "$PRIORITY" ]]; then
    JSON=$(echo "$JSON" | jq --arg v "$PRIORITY" \
        '. + {additionalAttributes: {priority: {name: $v}}}')
fi

# ---- Write temp file and edit via acli ----
TMPFILE=$(make_tmp_json "$JSON")
trap "rm -f $TMPFILE" EXIT

echo "Updating $KEY..." >&2
acli jira workitem edit --key "$KEY" --from-json "$TMPFILE" --json --yes

echo "Updated: $KEY" >&2
echo "{\"updated\": \"$KEY\"}"
