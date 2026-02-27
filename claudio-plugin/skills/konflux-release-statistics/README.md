# Konflux Release Statistics Skill

A Claude Code skill for analyzing Konflux application builds, releases, and integration tests in Kubernetes.

## Files

- **skill.md**: Complete skill documentation with methodology and commands
- **METHODOLOGY.md**: Detailed walkthrough of actions taken to generate statistics
- **README.md**: This file

## Quick Start

When analyzing a Konflux application release, follow this workflow:

### 1. Verify Application
```bash
kubectl get application <app-name> -n <namespace>
```

### 2. Gather Statistics
Use the commands documented in `skill.md` to collect:
- Build timeline and snapshot counts
- Stage and production release counts
- Integration test results
- Component deployment status

### 3. Generate Summary
Combine the data into a structured report covering:
- Timeline (first build → first production release)
- Build & release counts
- Integration test services and results
- Component release status

## Example Output

See `METHODOLOGY.md` for the full analysis workflow.

Typical metrics generated:
- **Time to production**: Days from first build
- **Build iterations**: Primary builds and total snapshots
- **Test coverage**: Snapshots tested and pass rate
- **Release breakdown**: Stage releases and production releases

## Integration with Claude Code

To use this skill:

1. Reference the skill when analyzing Konflux releases
2. Follow the step-by-step methodology in `skill.md`
3. Adapt queries for different application names and namespaces

## Requirements

- Kubernetes cluster access via `kubectl`
- Appropriate RBAC permissions for the namespace
- `jq` for JSON processing
- `python3` for calculations

## Customization

Modify the queries in `skill.md` to:
- Filter by different label selectors
- Include additional Konflux resources
- Change date/time calculations
- Add custom metrics

## Notes

- This skill is designed for Konflux/AppStudio workflows
- Assumes standard Konflux resource naming conventions
- Integration test results are stored in snapshot annotations
- Component suffixes (e.g., `-xy`) indicate retries/variants
