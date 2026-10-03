# Security model

FlowGuard starts fail-closed. SAP write access is disabled, each sensitive action has its own flag,
and human approval is required by default. Approval is bound to an exact action; it is not a generic
permission token. Idempotency prevents replay after a successful write.

For a real SAP tenant:

- use separate least-privilege technical identities for read and write;
- prefer Communication User/System/Arrangement where applicable;
- keep credentials in n8n credentials or a secret manager, never workflow exports;
- add API authentication and RBAC before exposing FlowGuard outside localhost;
- restrict outbound hosts and allowed write actions;
- replace the local database audit with retention-protected storage;
- redact business-partner and financial evidence from logs.

The current API has no end-user authentication and is therefore a local portfolio foundation, not
a production internet service.

