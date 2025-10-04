# Market Notifier (GitHub Actions + Telegram)

This project runs scheduled checks (GitHub Actions) and sends Telegram notifications:
- Intraday checks: 10:00, 12:00, 14:00, 15:00 IST (cron)
- End-of-day summary: 18:30 IST
- Crash triggers: Nifty drop <= -3% in that run → deploy next crash tranche and notify.
- State is persisted in `crash_state.json` and updated (committed) by workflow.

## Files
- `market_notifier.py` - main script
- `.github/workflows/market-notifier.yml` - scheduled workflow
- `requirements.txt` - Python deps
- `crash_state.json` - initial crash state

## Setup (summary)
1. Create a GitHub repository (public recommended to keep Actions free).
2. Add the files above and commit.
3. Create a Telegram Bot:
   - Talk to BotFather, `/newbot` → get `BOT_TOKEN`.
   - Message the bot from your account; get your chat id (inspect `https://api.telegram.org/bot<token>/getUpdates` or use a helper bot).
4. Add GitHub repo secrets:
   - `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
     - `TELEGRAM_BOT_TOKEN` = your bot token
     - `TELEGRAM_CHAT_ID` = your chat id
5. Manually run workflow once: Actions → Market Notifier → Run workflow → `workflow_dispatch` to test.
6. To test crash behaviour: temporarily change `CRASH_TRIGGER_PCT` in `market_notifier.py` to `-0.1` and run workflow manually, then revert back.

## Notes & improvements
- `yfinance` is a POC. Replace `fetch_market_data()` with a reliable Indian market data provider (NSE API, paid feed) if you need accuracy for Sensex/VIX/FII flows and top movers.
- If you prefer to avoid updating the repo for state persistence, use a gist / Google Sheet / small external store.
- For near-real-time alerts you will need an always-on runner (paid), e.g. Render, Railway, or Cloud Run.

## Troubleshooting
- If you don’t receive Telegram messages: confirm bot token & chat id are correct; check Actions logs for errors.
- If workflow push fails: ensure `actions/checkout` uses `persist-credentials: true` (it does), and your repo allows pushes from Actions.

