# Reproducible demo guide

## O2C: billing without FI

1. Activate `billing_without_fi` on `POST /mock/scenario/billing_without_fi`.
2. Run `POST /runs/o2c`.
3. Observe rule `SD002`, type `BILLING_WITHOUT_FI`, with billing and sales-order evidence.
4. Open the dashboard and explain that the decision is deterministic, not made by an LLM.

## P2P: supplier invoice above tolerance

1. Activate `po_price_variance`.
2. Run `POST /runs/p2p`.
3. Observe `MM005`: PO 100,000 versus invoice 107,500 at a 2% tolerance.
4. Create an approval for `release_supplier_invoice` but leave write flags disabled to demonstrate
   defense in depth.

## n8n boundary

Import the JSON exports only when ready. They are inactive, contain no credentials and call the
FlowGuard API. The first scaffold validates JSON structure but intentionally does not claim runtime
execution in n8n.

