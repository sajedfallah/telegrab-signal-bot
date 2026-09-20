# SIGNAL-AGENT — Release B: ICT Event Engine
Deterministic shadow/event-only layer over Release A. It persists normalized, rule-versioned ICT events and derived links. It has no setup scoring, TRADE/NO-TRADE, signal generation, Telegram publication or AI authority.

Implemented families: confirmed swing structure, liquidity pools/sweeps, displacement, three-candle FVG, MSS/CHOCH, displacement-linked order blocks, breakers, premium/discount, NEXUS Daily Quadrant (last 10 D1 candles, longest wick, newest wins ties, 25/50/75), and timezone-aware Asia/London/New York session context.

Event identity is SHA-256 over symbol/timeframe/type/direction/source-time/rule-version. INSERT OR IGNORE persistence makes restart/replay idempotent. Replay uses candle prefixes to reproduce closed-candle arrival.

Release B remains isolated from existing Signal Authority and AUTOTRADE-DATA-ANALYSIS.
