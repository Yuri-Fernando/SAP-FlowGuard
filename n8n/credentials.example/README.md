# Credential policy

Do not commit exported n8n credentials. Configure credentials in n8n or a secret manager.

- `SAP_READ`: read-only technical identity.
- `SAP_WRITE`: separate least-privilege write identity.
- `SAP_API_KEY`: Business Accelerator Hub sandbox key, injected into the API container.

The default mock mode needs no SAP credential.

