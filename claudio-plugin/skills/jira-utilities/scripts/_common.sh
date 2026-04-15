#!/usr/bin/env bash
#
# Common helpers for jira-utilities scripts.
# Sourced by all scripts in this directory.
#
# Required environment variables:
#   JIRA_SITE   - Atlassian site hostname (e.g., yourorg.atlassian.net)
#   JIRA_TOKEN  - API token from Atlassian account settings -> Security -> API tokens
#   JIRA_EMAIL  - Your Atlassian account email

# Validate required env vars and exit with code 1 if any are missing
require_env() {
    local missing=()
    for var in JIRA_SITE JIRA_TOKEN JIRA_EMAIL; do
        [[ -z "${!var:-}" ]] && missing+=("$var")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "ERROR: Missing required environment variables: ${missing[*]}" >&2
        echo "  JIRA_SITE  = Atlassian site hostname (e.g., yourorg.atlassian.net)" >&2
        echo "  JIRA_TOKEN = API token from Atlassian account settings" >&2
        echo "  JIRA_EMAIL = Your Atlassian account email" >&2
        exit 1
    fi
}

# Authenticate acli using env vars.
# acli stores credentials in ~/.config/acli/ after login.
# Skips the network round-trip if credentials for this site are already stored.
ensure_auth() {
    require_env
    if grep -qrs "$JIRA_SITE" "${HOME}/.config/acli/" 2>/dev/null; then
        return 0
    fi
    echo "$JIRA_TOKEN" | acli jira auth login \
        --site "$JIRA_SITE" \
        --email "$JIRA_EMAIL" \
        --token 2>/dev/null || {
        echo "ERROR: acli authentication failed. Verify JIRA_SITE, JIRA_EMAIL, and JIRA_TOKEN." >&2
        exit 4
    }
}

# Write JSON to a temp file and echo the path.
# Caller is responsible for cleanup (use: trap "rm -f $TMPFILE" EXIT).
make_tmp_json() {
    local json="$1"
    local tmp
    tmp=$(mktemp /tmp/acli-jira-XXXXXX.json)
    echo "$json" > "$tmp"
    echo "$tmp"
}
