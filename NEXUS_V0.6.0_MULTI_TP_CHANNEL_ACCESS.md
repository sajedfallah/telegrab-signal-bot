# NEXUS v0.6.0 — MT5 Signal Authority UI Update

## Changes

### 1. Channel / Access selector in MT5 Admin
The Signal tab now exposes the canonical MT5-admin destination selector:

- FREE
- VIP
- BOTH

The selection is persisted per MT5 account and is sent to the canonical `/api/v1/admin/mt5/signals` endpoint as `destination`.

Telegram remains non-operational for signal issuance in v0.6.0. The destination value is retained as signal scope/metadata for downstream access routing and reporting.

### 2. Multiple take-profit levels
The MT5 Admin Signal panel now accepts five sequential targets:

- TP1
- TP2
- TP3
- TP4
- TP5

TP1 is required. Later targets are optional but must be filled sequentially and ordered correctly for BUY/SELL geometry.

The backend already supports the canonical target ladder and can deliver up to ten targets to MT5; the v0.6.0 Admin UI exposes five for practical on-chart operation.

### 3. Target-aware trailing
Trailing profiles 5 and 7 now process the target ladder rather than only TP1/TP2:

- each reached intermediate target can partially reduce volume;
- TP1 moves the stop toward breakeven;
- later targets use the previous target as a trailing anchor;
- the final target closes the remaining position volume;
- target completion is persisted with `tpN_done` state for restart-safe management.

For four or more targets, the default partial allocation is evenly distributed across the target ladder, with the final target closing the remaining volume.

### 4. Safety
- No signal is issued unless FREE/VIP/BOTH is selected.
- Empty gaps in TP1..TP5 are rejected.
- BUY targets must increase above entry; SELL targets must decrease below entry.
- Existing API/default callers remain backward-compatible because destination defaults to BOTH.

## Verification

The updated source retains the existing test suite and adds four static regression tests for the new MT5 Authority / Multi-TP behavior.

