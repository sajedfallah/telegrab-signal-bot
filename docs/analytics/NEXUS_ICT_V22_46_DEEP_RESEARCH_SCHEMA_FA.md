# NEXUS ICT V22.46 — Deep Research Analytics Schema

## Research Features
File family:
`NEXUS_V22_46_RESEARCH_FEATURES_<SYMBOL>_<TF>.csv`

Groups:
1. Signal identity / NY timing
2. Daily CE metadata
3. Sweep / MSS / displacement sequence
4. FVG / mitigation
5. PDH/PDL + Asia liquidity map
6. volatility percentile / ADR / efficiency / tick-volume ratio
7. component quality scores

## Signal Horizons
`NEXUS_V22_46_SIGNAL_HORIZONS_<SYMBOL>_<TF>.csv`

Horizons: 1, 3, 5, 10, 20 bars.

Metrics:
- return R
- path MFE / MAE
- time-to-1R / 2R / SL
- hit flags
- same-bar 1R/SL ambiguity

## Counterfactual
`NEXUS_V22_46_COUNTERFACTUAL_<SYMBOL>_<TF>.csv`

Compared management paths:
- actual Trail07
- fixed TP 1R / 2R / 3R
- BE 0.75 / 1.0 / 1.25R with 2R target

## Analytical boundary
This telemetry is observational. It does not modify signal eligibility, gates, score weights, or execution rules automatically.
