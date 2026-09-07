# NEXUS Current Production

- Current production line: **NEXUS v0.6.5**
- Production baseline used on VPS: `feature/v065-integrated-release`
- Professional News Engine patch line: `feature/v065-professional-news-engine`
- General Agentic Content remains **disabled** by default.
- Public market runtime remains the authoritative delivery path for Public-channel news.

## Public news policy

Professional News Engine v1 is enabled by default and applies before Telegram publication:

- Focus: GOLD / BTC / DOW plus systemic macro events affecting those markets.
- Minimum publish score: 65/100.
- Important News: 80/100.
- Breaking: 90/100 plus Tier-A source and breaking-event confirmation.
- Tier-C sources are fail-closed pending confirmation.
- Persistent story de-duplication prevents restart re-posts.
- Article images are published only when image-confidence score passes the configured threshold.
- Morning quiet remains in force; only confirmed Breaking items bypass it.

This document is the repository marker for the version currently treated as the latest production version until a newer release is explicitly promoted.
