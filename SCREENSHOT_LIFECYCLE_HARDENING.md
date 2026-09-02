# NEXUS v0.5.8 — Screenshot Failure Hardening

- MT5 PENDING/OPEN/CLOSE lifecycle events no longer fail when chart capture is unavailable.
- Missing MT5 screenshots are treated as non-fatal; the backend logs a warning and continues the lifecycle.
- `build_chart_frame()` accepts empty chart bytes and produces a deterministic branded placeholder.
- Added the supplied NEXUS logo at `assets/branding/NEXUS_logo.png`.
- Added regression tests for screenshot-optional lifecycle handling and packaged branding.
