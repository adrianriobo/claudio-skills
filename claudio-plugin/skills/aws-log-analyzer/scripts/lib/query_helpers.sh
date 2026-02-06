#!/bin/bash
# CloudWatch Logs Insights query helpers

set -euo pipefail

# Wait for query to complete with progress indicator
# Usage: wait_for_query <query-id> [description]
wait_for_query() {
    local query_id="$1"
    local description="${2:-Query}"
    local status=""
    local count=0

    echo -n "$description: " >&2

    while true; do
        status=$(aws logs get-query-results --query-id "$query_id" --query 'status' --output text 2>/dev/null || echo "Failed")

        case "$status" in
            "Complete")
                echo " Done" >&2
                break
                ;;
            "Failed"|"Cancelled")
                echo " Failed" >&2
                return 1
                ;;
            "Running"|"Scheduled")
                echo -n "." >&2
                sleep 2
                count=$((count + 1))
                # Timeout after 60 seconds (30 iterations * 2s)
                if [ $count -gt 30 ]; then
                    echo " Timeout" >&2
                    return 1
                fi
                ;;
            *)
                # Unknown status, wait a bit more
                sleep 1
                ;;
        esac
    done

    # Get the results
    aws logs get-query-results --query-id "$query_id"
}

# Export functions
export -f wait_for_query
