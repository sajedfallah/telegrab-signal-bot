# NEXUS Runtime-05 — Signal Screenshot Only / Text Lifecycle

## Policy
- A chart screenshot is captured and published only when the original trading signal is issued.
- After signal issuance, lifecycle events are text-only replies to the original signal message.
- Applies to manual close, TP/SL close, Stop Out, trailing close, break-even/SL updates, partial close, and LIMIT activation/update events.
- MT5 lifecycle handlers do not call `CaptureChartBase64`.
- Backend lifecycle handlers do not read `chart_path` or call `build_chart_frame`.
- Manual admin signal-close flow no longer asks for a result image.
- UI hide/restore used by signal screenshot capture is therefore never invoked by post-signal lifecycle events.

## Expected flow
`ISSUE SIGNAL -> screenshot + signal post`
`OPEN/ACTIVATE/UPDATE/PARTIAL/CLOSE -> text reply only`

## Validation
Python test suite: 183 passed, 3 skipped.
