# n8n orchestration

The exported workflows in `workflows/` deliberately keep SAP rules out of n8n. They call the
FlowGuard API, which owns canonical mapping, correlation, deterministic rules, persistence,
approval checks, CSRF/ETag handling and audit.

## Import (when you are ready)

1. Start the stack with `docker compose up --build`.
2. Open `http://localhost:5678`.
3. Import each JSON file from `/workflows` (the same directory is mounted inside the container).
4. Confirm that `FLOWGUARD_API_URL=http://flowguard-api:8000` exists in the n8n container.
5. Execute manually before activating schedules.

No SAP credential is embedded in a workflow. In sandbox mode, `SAP_API_KEY` belongs only in the
FlowGuard API environment. The HTTP Request node is the primary adapter; community SAP nodes are
optional and are not required by these workflows.

These exports are structurally validated by `scripts/validate_workflows.py`. They have not been
executed against a running n8n instance in the initial scaffold.

