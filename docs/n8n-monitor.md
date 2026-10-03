# n8n flow monitor

The dashboard at `http://localhost:8501` has two monitoring levels:

1. **No n8n API key:** it checks `/healthz` and continues showing FlowGuard exceptions, approvals,
   SAP mode, provider health and financial risk.
2. **With an n8n API key:** it also reads the official n8n public API and displays workflow state
   plus the 30 most recent executions.

## Enable workflow and execution history

1. Start n8n and create an API key under **Settings > n8n API**.
2. Put the key only in the local `.env` file:

   ```dotenv
   N8N_API_KEY=replace-with-your-local-key
   ```

3. Recreate only the dashboard container:

   ```powershell
   docker compose up -d --build flowguard-dashboard
   ```

The key is injected into the dashboard backend and is never returned to the browser. The backend
uses `X-N8N-API-KEY` with `/api/v1/workflows` and `/api/v1/executions`.

If the key is absent, invalid or the n8n API is unavailable, the dashboard degrades gracefully and
shows a diagnostic message instead of failing the whole control tower.

## Scope and security

This is a local portfolio monitor. Before exposing it outside localhost, add authentication, RBAC,
TLS and network restrictions to both the FlowGuard API and dashboard.

