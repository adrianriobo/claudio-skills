# Konflux Release Statistics - Action Summary

## Actions Taken to Generate Release Statistics

### Phase 1: Application Discovery
**Goal**: Verify the application exists and get basic info

1. **Check for application**
   ```bash
   kubectl get applications -n <namespace> | grep <app-name>
   ```
   - Example output: `<app-name>` (24 days old)

### Phase 2: Resource Counting
**Goal**: Get high-level counts of builds and releases

2. **Count components**
   ```bash
   kubectl get components -n <namespace> -l 'app.kubernetes.io/instance=<app-name>' --no-headers | wc -l
   ```
   - Example result: 0 components found (components not labeled this way)

3. **Count snapshots (builds)**
   ```bash
   kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' --no-headers | wc -l
   ```
   - Example result: **49 snapshots**

4. **Count releases**
   ```bash
   kubectl get releases -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' --no-headers | wc -l
   ```
   - Example result: **29 releases**

### Phase 3: Timeline Analysis
**Goal**: Determine build timeline and time to production

5. **List releases sorted by creation time**
   ```bash
   kubectl get releases -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' --sort-by=.metadata.creationTimestamp
   ```
   - Identified stage releases (e.g., product-stage-version)
   - Identified production releases (e.g., product-prod-version, product-tech-preview-prod-version)

6. **Get first snapshot timestamp**
   ```bash
   kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
     jq -r '.items | sort_by(.metadata.creationTimestamp) | .[0] | .metadata.creationTimestamp'
   ```
   - Example result: **2026-02-03T05:20:02Z**

7. **Get first production release timestamp**
   ```bash
   kubectl get releases -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
     jq -r '.items[] | select(.spec.releasePlan | contains("prod")) | .metadata.creationTimestamp' | sort | head -1
   ```
   - Example result: **2026-02-24T19:13:12Z**

8. **Calculate time to production**
   ```python
   python3 -c "print(round(1864390 / 86400, 1))"
   ```
   - Example result: **21.6 days**

### Phase 4: Release Categorization
**Goal**: Separate stage from production releases

9. **Count stage releases**
   ```bash
   kubectl get releases -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
     jq -r '.items[] | select(.spec.releasePlan | contains("stage")) | .metadata.name' | wc -l
   ```
   - Example result: **23 stage releases**

10. **List production releases**
    ```bash
    kubectl get releases -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
      jq -r '.items[] | select(.spec.releasePlan | contains("prod")) | .metadata.name'
    ```
    - Example: Found 6 production releases for various components

### Phase 5: Build Analysis
**Goal**: Understand build iterations and retries

11. **Count primary builds (excluding retries)**
    ```bash
    kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
      jq -r '.items[] | .metadata.name' | grep -v '\-[a-z0-9]\{2\}$' | wc -l
    ```
    - Example result: **24 primary builds**
    - Inference: Calculate component-specific builds/retries (total snapshots - primary builds)

### Phase 6: Integration Test Discovery
**Goal**: Find what tests were run on the builds

12. **Check snapshot test status messages**
    ```bash
    kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
      jq -r '[.items[].status.conditions[] | select(.type=="AppStudioTestSucceeded") | .message] | unique[]'
    ```
    - Common status messages:
      - "All Integration Pipeline tests passed"
      - "No required IntegrationTestScenarios found, skipped testing"

13. **Count snapshots with integration tests**
    ```bash
    kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
      jq -r '.items[] | select(.status.conditions[] | select(.type=="AppStudioTestSucceeded" and .message=="All Integration Pipeline tests passed")) | .metadata.name' | wc -l
    ```
    - Example result: **15 snapshots** ran integration tests

### Phase 7: Test Results Extraction
**Goal**: Extract detailed test results from snapshot annotations

14. **Examine test status annotation structure**
    ```bash
    kubectl get snapshot <snapshot-name> -n <namespace> -o jsonpath='{.metadata.annotations.test\.appstudio\.openshift\.io/status}' | jq '.'
    ```
    - Discovered JSON array format with scenario, status, timestamps, pipeline run names

15. **Extract all test scenarios and counts**
    ```bash
    for snap in $(kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o jsonpath='{.items[*].metadata.name}'); do
      kubectl get snapshot $snap -n <namespace> -o jsonpath="{.metadata.annotations.test\.appstudio\.openshift\.io/status}"
    done | grep -v '^$' | jq -r '.[].scenario' | sort | uniq -c | sort -rn
    ```
    - Example results:
      - test-scenario-1: 34 runs
      - test-scenario-2: 7 runs
      - test-scenario-3: 5 runs

16. **Extract test pass/fail breakdown**
    ```bash
    for snap in $(kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o jsonpath='{.items[*].metadata.name}'); do
      kubectl get snapshot $snap -n <namespace> -o jsonpath="{.metadata.annotations.test\.appstudio\.openshift\.io/status}"
    done | grep -v '^$' | jq -r '.[] | "\(.scenario)|\(.status)"' | sort | uniq -c | sort -k2
    ```
    - Example results showing pass/fail counts per scenario

### Phase 8: Integration Test Scenario Details
**Goal**: Understand what each test does

17. **List all integration test scenarios**
    ```bash
    kubectl get integrationtestscenario -n <namespace> | grep <app-name>
    ```
    - Example: Found 3 scenarios for the application

18. **Get detailed configuration for each test**
    ```bash
    kubectl get integrationtestscenario <test-scenario-name> -n <namespace> -o yaml
    ```
    - Extracted for each scenario:
      - Test purposes and components tested
      - Pipeline locations (e.g., konflux-data repo)
      - Test parameters (architecture, specific versions, etc.)
      - Optional flag status

### Phase 9: Component Identification
**Goal**: Identify all components built and released

19. **Get unique components from snapshots**
    ```bash
    kubectl get snapshots -n <namespace> -l 'appstudio.openshift.io/application=<app-name>' -o json | \
      jq -r '.items[].spec.components[].name' | sort -u
    ```
    - Example: Found 7 unique components across all builds

20. **Cross-reference with production releases**
    - Identified components built but not released to production (if any)

## Key Insights from Analysis

Typical insights to look for:
1. **Test Coverage Gap**: What percentage of snapshots had integration tests run
2. **Test Period**: When tests were active vs auto-release periods
3. **Optional Tests**: Whether tests are optional, allowing release despite failures
4. **Component Variance**: Components built but not released to production
5. **Success Rate**: Overall test pass rate and failure patterns

## Data Sources Used

1. **Applications**: Application metadata
2. **Snapshots**: Build artifacts with test results in annotations
3. **Releases**: Stage and production deployment records
4. **IntegrationTestScenarios**: Test definitions and configurations

## Tools Required

- `kubectl`: Kubernetes cluster access
- `jq`: JSON parsing and filtering
- `python3`: Date arithmetic
- `grep`, `sort`, `wc`: Text processing
