# Store and technician workflow fixes - 2026-11-07

- City-only selection for repairer profiles; backend normalizes county input to its city and prevents changing city while associated to another city's store.
- Multi-store technician membership uses existing store_staff. PC and mini-program team editors select city-scoped candidates; legacy default technicians remain compatible until explicit team save. Removing membership preserves assigned orders and wage history.
- Manual dispatch validates store ownership and membership. Repairer lists include assigned orders before acceptance and accepted jobs before service starts.
- Per-order WageRecord stores order/store/employee identities. Monthly SettlementItem is unique per month/store/employee in existing service logic; actor checks now prevent another manager issuing wages for a foreign store. Tests cover one technician in two stores with distinct monthly wage amounts.
- Independent phone/PC foreground polling every 20 seconds alerts pending acceptance and paid-pending-review orders. It does not implement background WeChat subscription messages.
- Customer payment no longer calls staff-only config diagnostics; payment creation retains all readiness, amount and fresh WeChat login validation. Actual payment requires user confirmation on a device.
- Referral QR server was verified to return an image. Client now downloads to a local temporary file and previews it, with explicit failure messages and base URL fallback.

Validation: multi-store membership and wage tests; customer payment UI test; order authorization 15/15; bill revision 12/12; WeChat resilience 9/9; store dashboard, referral UI and mini bill-revision tests. New API reads verified online (team/candidates/alerts all HTTP 200). Production payment readiness true; no real payment executed.

Deployment: /www/wwwroot/xiulijiu_api/releases/20261107-store-chain. Backup: /www/wwwroot/xiulijiu_api/backups/pre-20261107-store-chain. Restarted only xiulijiu-api.service. No schema changes. Preserved 22 users, 3 stores, 3 orders, 5058 catalog addresses, 12 service ranges. Existing orphan order_logs row 81 was present before deployment and left unchanged.

Mini-program development version uploaded: 2026.11.07.1. User performs review submission/release. Existing repairers lacking city must be completed via Modify City before selection; no city guessed for them.
