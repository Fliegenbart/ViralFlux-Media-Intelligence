# Hook Helpers

These scripts are repo-owned guardrails.
They are not wired automatically by this repo; they are intended to be connected to a local Claude workflow or used manually.

Current helpers:

- `guard-sensitive-paths.sh`
  blocks risky edits unless explicitly allowed
- `validate-ml-changes.sh`
  runs targeted backend validation for regional forecast changes
- `validate-cockpit-ui.sh`
  runs targeted frontend validation for cockpit changes
- `validate-deploy-changes.sh`
  performs a light sanity check for deployment script changes

Each script accepts changed file paths as arguments.
If no arguments are passed, the script derives changed files from git.

