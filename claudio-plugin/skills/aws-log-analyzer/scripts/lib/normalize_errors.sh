#!/bin/bash
# Error message normalization library
# Normalizes error messages by replacing timestamps, IPs, IDs with placeholders

set -euo pipefail

# Normalize a single error message
# Usage: normalize_error_message "<message>"
normalize_error_message() {
    local message="$1"

    # Replace timestamps (various formats)
    message=$(echo "$message" | sed -E 's/[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?/<TIMESTAMP>/g')
    message=$(echo "$message" | sed -E 's/[0-9]{2}\/[0-9]{2}\/[0-9]{4}/<TIMESTAMP>/g')

    # Replace UUIDs
    message=$(echo "$message" | sed -E 's/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/<UUID>/gi')

    # Replace IP addresses
    message=$(echo "$message" | sed -E 's/[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/<IP>/g')

    # Replace common ID patterns
    message=$(echo "$message" | sed -E 's/(user|id|request|session|trace)_[0-9a-zA-Z]+/\1_<ID>/gi')
    message=$(echo "$message" | sed -E 's/(user|id|request|session|trace):[0-9a-zA-Z]+/\1:<ID>/gi')

    # Replace numbers in common contexts
    message=$(echo "$message" | sed -E 's/line [0-9]+/line <NUM>/gi')
    message=$(echo "$message" | sed -E 's/port [0-9]+/port <NUM>/gi')

    # Replace file paths (simple version)
    message=$(echo "$message" | sed -E 's/\/[a-zA-Z0-9_\/-]+\.(log|txt|json|yaml|yml)/<FILE>/g')

    echo "$message"
}

# Normalize CloudWatch Insights error results
# Input: JSON array from CloudWatch Insights with flattened structure
# Output: Normalized JSON with pattern field added
normalize_insights_errors() {
    local json_input="$1"

    echo "$json_input" | jq '[
        .[] | . + {
            pattern: (.message | gsub("[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?"; "<TIMESTAMP>")
                               | gsub("[0-9]{2}/[0-9]{2}/[0-9]{4}"; "<TIMESTAMP>")
                               | gsub("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"; "<UUID>"; "i")
                               | gsub("[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}"; "<IP>")
                               | gsub("(user|id|request|session|trace)_[0-9a-zA-Z]+"; "\\1_<ID>"; "i")
                               | gsub("(user|id|request|session|trace):[0-9a-zA-Z]+"; "\\1:<ID>"; "i")
                               | gsub("line [0-9]+"; "line <NUM>"; "i")
                               | gsub("port [0-9]+"; "port <NUM>"; "i")
                               | gsub("/[a-zA-Z0-9_/-]+\\.(log|txt|json|yaml|yml)"; "<FILE>"))
        }
    ]'
}

# Export functions
export -f normalize_error_message
export -f normalize_insights_errors
