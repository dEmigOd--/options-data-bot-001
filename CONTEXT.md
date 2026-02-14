# Context – SPX Options (session summary)

**Date:** 2026-02-11  
**Status:** Done for today. Use this file to resume context later.

---

## What’s in the project

- **Collector** – Fetches SPX options chain from IBKR every minute, stores in SQL Server.
- **UI (main)** – Pick expiration / call|put / strike, view price vs time from DB.
- **Position Builder** – Live multi-leg builder: ticker, expirations from IBKR, add legs (strike, call/put, buy/sell), bid/ask/delta, lazy & smart bot composite price, P&L-at-expiration chart. Run: `.\run_position_builder.ps1`.

---

## Position Builder – current state

- **Layout:** Two columns (~50/50). Left: API connection, Underlying (ticker + Load expirations), Expiration calendar, P&L at expiration (under calendar). Right: Add leg, Legs table, Composite price, Refresh prices, Status bar. Content in scroll area.
- **Default size:** 1173 × 732 (hardcoded `DEFAULT_FORM_WIDTH`, `DEFAULT_FORM_HEIGHT` in `position_builder.py`). Min 900×520.
- **Legs table:** Min height 320, max 520. Bid/Ask/Delta read-only; editing Expiration/Strike/Type/Action/Mult triggers same logic as Edit (merge or replace, sort, refresh).
- **Pricing:** Lazy bot (buy=ask, sell=bid); smart bot (mid). Debit red, credit blue. Cost basis for P&L chart = lazy total.
- **IBKR:** Separate client IDs for expirations vs quotes (`config.py`: `IBKR_CLIENT_ID`, `IBKR_CLIENT_ID_QUOTES`). Leg-only quotes, 5s refresh, add-leg triggers refresh. Delta from Greeks.
- **P&L chart:** Optional (PyQt6-Charts). Intrinsic at expiry vs underlying; cost basis = lazy total. If package missing, P&L section hidden.
- **Docs:** README has Position Builder section + run instructions. `docs/RUN_POSITION_BUILDER.md` – how to run, what you see, “How it works” (connection, workers, pricing, legs/quotes, P&L).

---

## Commits

- **Branch:** `feature/position-builder-ui`. Many changes not yet committed.
- **COMMITS.md** – At top: “This branch: position-builder UI” with suggested single commit (files to add, message, `git add` + `git commit` commands). Rule: you review and run the commit yourself.

---

## Key paths

- `src/spx_options/ui/position_builder.py` – Position Builder window (layout, defaults, close).
- `src/spx_options/position/` – builder_service, pnl_curve, leg, pricing.
- `src/spx_options/suppliers/ibkr.py` – strikes, leg quotes, delta.
- `docs/RUN_POSITION_BUILDER.md` – run + how-it-works.
- `run_position_builder.ps1` – launcher (uses `.venv`, `PYTHONPATH=src`).

---

## Next time

- Run and commit when ready (see COMMITS.md).
- No open bugs or tasks noted for today.
