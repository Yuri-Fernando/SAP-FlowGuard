# Architecture and implementation boundaries

The FlowGuard API is the business-control boundary. n8n schedules and routes work, while the API
owns canonical mapping, correlation, rules, severity, approvals, idempotency and audit. This keeps
the same controls in place if orchestration later moves to SAP Build, Joule Studio/managed n8n,
Event Mesh or another engine.

## Provider selection

- `MockSapProvider`: full local behavior and controlled write simulation.
- `SapSandboxProvider`: API-key authenticated, read-only Accelerator Hub access.
- `HybridSapProvider`: composes sandbox reads with mock writes and labels the target.
- `live`: reserved until communication arrangements and tenant contracts are known.

Capability discovery exposes what a configured provider can actually do. It does not infer write
support from the existence of an entity set.

## Data path

1. A workflow calls `/runs/o2c`, `/runs/p2p` or `/runs/fi`.
2. The provider follows OData pagination and maps SAP-shaped fields to canonical documents.
3. The rules engine correlates canonical documents and returns evidence-backed exceptions.
4. Persistence deduplicates open rule/document pairs and records an audit event.
5. Sensitive remediation uses a separate approval and `/writebacks` request.

Raw payloads are available transiently to mappers but excluded from the canonical API model.

## Next increments

- metadata-driven capability probes and contract snapshots;
- Goods Receipt and item-level quantity correlation;
- SOAP adapter for `JournalEntryCreateRequestConfirmation_In`;
- Redis locks, retries and DLQ workers;
- HANA repository implementation;
- AI Analyst with the policy “explain, do not authorize”;
- Prometheus metrics and immutable audit sink;
- tenant-specific live authentication adapters.

