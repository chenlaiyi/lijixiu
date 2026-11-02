# Coverage reassignment fix - 2026-11-02

Cause: four saved precise coverage rows for store 14 refer to disabled legacy catalog addresses (119-122). The tree hid those addresses but retained their rules in the save payload. Server validation correctly rejected the replacement request.

Fix: remove disabled, missing, pending-review or wrong-estate precise references when building the allocation draft. Preserve valid precise assignments and all existing hierarchical selection behavior. Update static cache versions.

Validation: address-tree regression covers stale hidden references, clearing selection, reselecting and reopening saved scopes. Scope-category, unified-catalog and client-cascade suites passed. Public frontend files match workspace bytes.

Deployment: updated only admin-web/address-tree.js and index.html in current release 20261102-catalog-tree. No service restart. Database and original frontend backed up at /www/wwwroot/xiulijiu_api/backups/coverage-reassign-20261102083458. The four persisted coverage rows were verified unchanged; the administrator decides the replacement scope on the next successful save. No mini-program upload needed.
