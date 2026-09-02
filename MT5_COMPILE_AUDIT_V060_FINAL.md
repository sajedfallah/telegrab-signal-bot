# NEXUS v0.6.0 — MT5 Compile Audit / Final Source Patch

## Scope
Reviewed the v0.6.0 Multi-TP / Channel-Access source package supplied for MetaEditor compilation.

## Root cause of the reported 96/32 errors
The reported MetaEditor errors all pointed to `TrailingEngine.mqh` and repeatedly referenced `CNexusTrailingEngine::G` / `CNexusTrailingEngine::S` as private/non-static members. The original patch declared these helpers as class-static members and placed them across access sections. Some MetaEditor parser/compiler builds can mis-handle that arrangement when the header is expanded through nested includes.

### Final correction
`Prefix`, `G`, and `S` were removed from `CNexusTrailingEngine` and replaced with file-scope, uniquely named helpers:
- `NexusTrailPrefix()`
- `NexusTrailGet()`
- `NexusTrailSet()`

All trailing-engine state access now uses these file-scope helpers. This removes the class access/static lookup ambiguity entirely.

## Error categories
### Syntax errors
No direct syntax defect was found in the reviewed MQL5 source after the helper refactor. The reported errors were compiler semantic/access diagnostics rather than malformed punctuation or missing delimiters.

### Linker errors
MQL5 EA source does not use a conventional separate linker stage like C/C++. The relevant failure mode here was compile-time member lookup, not a linker failure.

### Semantic / compiler errors
Resolved:
- `G - cannot access private member function`
- `S - access to non-static member or function`
- repeated references to `CNexusTrailingEngine::G/S`

### Runtime-safety issues found and corrected
- Admin signal issuance now rejects `risk <= 0`, preventing creation of signals that the client execution engine would later reject.
- For MARKET admin signals, if Entry is left at zero, the EA resolves Entry from current Ask/Bid before issuing the canonical signal.
- Channel destination is now enforced as an MT5 client audience scope: FREE/BOTH are visible to eligible AutoTrade clients; VIP requires active VIP entitlement. Telegram is not used as a signal transport.
- EA release metadata is consistent: property version `1.60`, runtime EA version `0.6.0`.

## Multi-TP verification
The EA panel exposes TP1..TP5. The backend accepts up to 10 canonical targets. Target ordering and BUY/SELL geometry are validated. The trailing engine persists `tpN_done` state and processes the target ladder sequentially. Intermediate targets may partially close volume; the final target closes the remaining position.

## Channel Access verification
Admin UI exposes FREE / VIP / BOTH. Destination is persisted with the signal. Client-side signal visibility is filtered after authentication, with VIP visibility dependent on active VIP entitlement.

## Signal Authority verification
The canonical admin endpoint is:
`POST /api/v1/admin/mt5/signals`

The endpoint requires MT5 admin authentication and creates signals with `issuer_type='MT5_ADMIN'`. Client polling only selects active signals with `issuer_type='MT5_ADMIN'`. Telegram signal creation/publication handlers are disabled at runtime.

## Tests
Final package Python/static suite:
- 167 passed
- 3 skipped

Python `compileall` passed.
Release static checks passed.

## Important certification boundary
A Python/static suite cannot prove that a specific installed MetaEditor build will emit zero MQL5 warnings. The final certification step remains pressing F7 on the exact copied EA source and its Include tree in the target terminal. The source package has been hardened specifically against the member-access errors shown in the supplied screenshots.
