NEXUS v7.1.2 — UI ACTIONS FINAL REVISED

Changes:
- Main customer menu changed to a compact 2-column task grid.
- Purchase Subscription is promoted into the main dashboard.
- AutoTrade and Account are paired as primary service/account actions.
- Payments and Referral are kept under Account, as requested.
- Removed the duplicate "My Points" button that routed to the same Referral action.
- Account menu now uses a single clear Buy/Renew Subscription action.
- English remains behind the language switch; Persian is the default Persian UI.
- Existing callback IDs and handlers were preserved to avoid breaking navigation.
- Three commercial purchase services remain:
  VIP / AutoTrade Expert / VIP + AutoTrade Expert.

Validation performed on the source tree:
- pytest: 64 passed, 3 skipped, 0 failed.
- Existing UI navigation/static callback tests remain green.
