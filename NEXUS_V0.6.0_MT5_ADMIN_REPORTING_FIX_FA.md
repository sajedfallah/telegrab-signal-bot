# NEXUS v0.6.0 — MT5 Authority / Telegram Reporting Fix

## Changes
- Minimize on the MT5 admin panel now removes every admin signal-form chart object; only the compact title/status bar remains.
- Telegram admin Signal Center is reporting-only: Active Signals, Closed Results, Signal Stats and Analytics.
- Telegram signal creation, publication, retry, and mutation callbacks remain disabled at runtime.
- Active/closed/statistics views are restricted to `issuer_type='MT5_ADMIN'` records.
- Signal detail in Telegram is read-only; no BE/SL/TP/Trailing/Close/Cancel controls are exposed.
- Signal ID is server-generated (`NX-0001`, `NX-0002`, ...) and is not entered by the MT5 administrator during issuance.
- MT5 management field is labeled `EXISTING SIGNAL ID` to distinguish it from issuance.
