# NEXUS ICT V22.42 — Signal Data & Telemetry Schema

## اصل طراحی

این Data Layer باید بتواند بعداً پاسخ دهد:

- کدام Feature واقعاً Expectancy را بالا می‌برد؟
- Daily CE چقدر Edge دارد؟
- CE50 یا CE75 کدام بهتر است؟
- چه ساعتی Signalها بهتر عمل می‌کنند؟
- Spread و slippage چه اثری دارند؟
- MFE/MAE نشان می‌دهد SL/TP/Trail چگونه باید اصلاح شود؟
- چه Setupهایی Confirm می‌شوند ولی در Execution رد می‌شوند؟
- تفاوت Signal Quality و Execution Quality چیست؟

هیچ فیلتر جدیدی از این Schema ساخته نمی‌شود مگر بعد از Sample کافی و review انسانی.

---

## Dataset: Signal Snapshot

Primary join keys:
- signal_id برای Confirmed Signal
- setup_key = signal_time + direction برای evaluated setup

### Identity
- event
- setup_key
- signal_id
- symbol
- timeframe
- direction
- stage
- reject_reason

### Time Context
- server_time
- utc_time
- ny_time
- ny_weekday
- ny_hour
- ny_minute
- session
- signal_age_sec

### Market / Broker Runtime
- bid
- ask
- spread_points
- spread_atr
- tick_age_sec
- terminal_ping_us
- stops_level
- freeze_level
- volume_min
- volume_step
- volume_max

### Signal Quality
- score
- grade
- signal_class
- market_regime
- execution_quality
- q_htf
- q_liquidity
- q_structure
- q_poi
- q_timing
- q_environment
- q_daily_ce

### Daily CE / Quadrant
- daily_ce_active
- daily_ce50
- daily_ce75
- entry_to_ce50_atr
- entry_to_ce75_atr
- ce_strength_atr

### Trade Plan
- entry
- planned_entry
- sl
- tp1
- tp2
- tp3
- risk_atr
- rr

### POI / Imbalance
- poi_top
- poi_bottom
- poi_mid
- entry_to_poi_mid_atr
- fvg_top
- fvg_bottom
- fvg_fill_pct
- fvg_strength_atr
- fvg_state
- ob_top
- ob_bottom
- ob_size_atr
- ob_state
- ote_low
- ote_high
- entry_to_ote_mid_atr

### Liquidity / ICT Rules
- liquidity_price
- liquidity_count
- liquidity_touches
- external_liquidity
- rule_sweep
- rule_mss_choch
- rule_fvg
- rule_mitigation
- first_mitigation
- rule_ob
- rule_idm
- rule_ote
- rule_volume
- rule_daily_liq
- rule_asian_liq
- rule_equal_liq
- rule_macro
- rule_structure_trend
- rule_htf_structure
- rule_news_clear
- silver_bullet

### Market State
- efficiency_ratio
- adr_usage
- atr

### Signal Candle
- candle_open
- candle_high
- candle_low
- candle_close
- candle_range_atr
- body_atr
- upper_wick_atr
- lower_wick_atr
- tick_volume
- tick_volume_ratio

### Account State
- balance
- equity
- free_margin
- margin
- margin_level
- leverage
- open_strategy_positions
- trade_enabled
- terminal_trade_allowed
- account_trade_allowed
- connected

---

## Dataset: Lifecycle Events

Join key:
- signal_id
- position_id after broker fill

Fields:
- event
- server / UTC / NY time
- session
- detail
- lifecycle
- signal_score
- execution_quality
- bid / ask / spread
- current price
- planned entry
- slippage points
- slippage ATR
- volume
- closed volume
- SL
- TP
- floating P/L
- realized delta
- MFE R
- MAE R
- account state

---

## Dataset: Closed Trade Analytics

Fields:
- position_id
- signal_id
- open / close time
- duration
- signal class
- regime
- Daily CE
- score
- feature fingerprint
- net P/L
- result R
- MFE R
- MAE R

Feature fingerprint currently supports:
- CE
- FVG
- RTO
- OTE
- OB
- Killzone
- REV
- CONT
- RANGE
- TREND
- SWEEP
- MSS
- CE50
- CE75

---

## Recommended analysis order

1. Minimum sample-size checks.
2. CE vs No-CE.
3. CE50 vs CE75.
4. Reversal vs Continuation.
5. Time-of-day / day-of-week.
6. Spread and slippage buckets.
7. FVG fill / POI distance.
8. Tick-volume ratio.
9. Candle body/wick profile.
10. MFE/MAE optimization for SL/TP/Trail.

Weights should not be changed automatically from a small sample.
