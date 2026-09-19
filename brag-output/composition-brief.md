# NEXUS Launch Video V1 — Composition Brief

## Master
- Canvas: 1080x1920 (9:16)
- FPS: 30
- Duration: 22s / 660 frames
- Audio: no voiceover in V1; optional restrained electronic bed
- Safe area: keep critical text inside x=90..990 and y=150..1710
- Visual source: current NEXUS Mini App on `feature/brag-video-v1`

## Asset map
- Brand logo: `miniapp/assets/brand/nexus-logo.svg`
- Brand mark: `miniapp/assets/brand/nexus-mark.svg`
- Landing visual: prefer the asset actually referenced by the current landing implementation; approved brand alternatives live under `miniapp/assets/brand/`
- Product UI: render/capture from `miniapp/`; do not redraw a fake product UI
- Live chart scene: use the real `charts` route. Do not inject fabricated XAU/Forex values.

## Motion system
- Default easing: cubic-bezier(.22,.8,.22,1)
- UI entrance: opacity 0→1 + translateY 28→0 over 10–14 frames
- Camera push: scale 1.00→1.055 over 70–110 frames
- Cyan glow: low amplitude only; never bloom over readable UI
- Scene transitions: 8–12 frame masked dissolve / directional push
- Avoid spins, glitch spam, aggressive zooms and generic crypto effects

## Timeline

### S01 — Landing / Brand
Frames: 0–89 (0.0–3.0s)
Visual: current NEXUS landing screen/brand artwork.
Camera: slow 1.00→1.045 push.
Overlay at f18: `NEXUS`; at f30: `Trading Intelligence`.
At f70 begin transition toward app shell.

### S02 — Home
Frames: 90–209 (3.0–7.0s)
Visual: real Home route.
Start slightly above center so top bar and primary dashboard are visible.
Overlay: `Your Trading Hub`.
Animation: overlay enters f108–120; subtle UI depth/parallax until f190.
Transition: focus movement toward bottom navigation.

### S03 — Signal Center
Frames: 210–329 (7.0–11.0s)
Visual: real Signals route.
Navigation tap/pulse on Signals at entry.
Highlight Free then VIP with a restrained focus ring; no fake P/L or win-rate.
Overlay: `Signals. Clear. Connected.`
Exit: horizontal mask toward Charts nav item.

### S04 — Live Charts Hero
Frames: 330–479 (11.0–16.0s)
Visual: real Charts route and real chart component.
Hero framing: candlestick panel + symbol chips + timeframe chips + connection/status area.
Sequence target: BTC then XAU; 5m then 15m only when the real UI/data path supports the state during capture/render.
Overlay: `Live Market. One Screen.`
Do not hardcode a market price into the video composition.
If XAU live data is unavailable, keep XAU identity visible but do not present synthetic candles/prices as live.

### S05 — Plans / AutoTrade
Frames: 480–569 (16.0–19.0s)
Visual: real Plans/Subscriptions route and existing AutoTrade product path.
Overlay: `From Signal to Execution`.
Use product UI only; do not animate a fabricated profitable trade.
Transition out with UI dim + brand mark emergence.

### S06 — Outro
Frames: 570–659 (19.0–22.0s)
Background: NEXUS deep navy/black.
Brand mark/logo centered.
Headline: `NEXUS`
Tagline: `Signals • Charts • Execution`
Motion: logo scale .94→1.00 and opacity 0→1; subtle cyan glow peaks around f610 then decays.
Hold final identity for at least 30 frames.

## Capture requirements
1. Use a mobile viewport matching the Mini App proportions.
2. Capture UI at high pixel density; no browser chrome.
3. Hide developer/debug overlays.
4. Never expose Telegram IDs, tokens, account secrets, license keys, `.env`, backend diagnostics or private user data.
5. Prefer deterministic demo-safe states for non-market account content.
6. Market content must respect the repository's real providers/source-of-truth rules.

## Typography
- Persian UI: existing Vazirmatn setup from Mini App.
- Brand/English overlays: clean geometric sans compatible with current NEXUS visual language.
- Overlay max: 2 lines.
- Minimum apparent mobile size: ~38 px for hero overlay text at 1080x1920.

## Color direction
Derive colors from current NEXUS CSS/assets rather than inventing a new palette: deep navy/black surfaces, white primary type, muted blue-gray secondary type, cyan/teal accent.

## Render QA
- Exactly 1080x1920, 30 fps.
- No clipped RTL text.
- No unreadable UI under glow/blur.
- No synthetic XAU/Forex market values.
- No profit guarantees/performance claims.
- Charts scene receives the longest uninterrupted screen time.
- Final brand frame holds cleanly for >=1 second.
