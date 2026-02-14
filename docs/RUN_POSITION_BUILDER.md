# How to run the Position Builder UI

Run the Position Builder with **no prompts**: a single script launches the form.

## Prerequisites

1. **Python 3.9+** and a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
2. **TWS or IB Gateway** running and logged in (for live prices). The app uses the same IBKR settings as the rest of the project (e.g. `.env`: `IBKR_HOST`, `IBKR_PORT`).

## Run (no input required)

From the **project root**:

```powershell
.\run_position_builder.ps1
```

This sets `PYTHONPATH=src` and runs `python -m spx_options.ui.position_builder`. The UI window opens; no further input is needed to start.

## What you see

1. **Ticker** – Default is SPX. You can change it (current backend is SPX-only).
2. **Load expirations** – Click to fetch expirations from IBKR (runs in background). Connection is also attempted when the window opens.
3. **Expiration calendar** – Click a **highlighted** date (blue/bold) to select that expiration. Use the calendar’s month/year controls to navigate. Highlighted dates are available expirations (weekly and monthly).
4. **Add leg** – Enter strike, choose Call/Put and Buy/Sell, then **Add leg**. Repeat for each leg.
5. **Legs table** – Shows Expiration, Strike, Type, Action, Mult, **Bid**, **Ask** (prices filled when refresh succeeds).
6. **Lazy bot price** – Debit (red) or credit (blue): buy legs use ask, sell legs use bid; total = debits − credits.
7. **Smart bot price** – Same total logic using mid price per leg; red/blue for debit/credit.
8. **Refresh prices** – Manual refresh; a timer also refreshes every 5 seconds when connected and you have legs.
9. **Status bar** (bottom) – Price/connection errors appear here in **red** (no popup). Clear when prices load successfully.
10. **P&L at expiration** (left column, under calendar) – Chart of P&L vs underlying price at expiry; cost basis = lazy bot total. Requires `PyQt6-Charts` (in `requirements.txt`; install with project venv if missing).

## How it works

- **Connection** – The app uses two IBKR API client IDs: one for loading expirations (and connection status), one for option quotes. This avoids "client id already in use" when both run. You can override them in `.env` with `IBKR_CLIENT_ID` and `IBKR_CLIENT_ID_QUOTES`.
- **Workers** – Expirations are loaded in a background thread when you open the window or click "Load expirations". Quotes for the current legs are fetched in another worker; the UI stays responsive. Adding a leg triggers an immediate quote refresh; a 5-second timer also refreshes prices for all active legs while connected.
- **Pricing** – **Lazy bot price**: for each leg, buy uses ask and sell uses bid; total = sum of debits (buys) minus sum of credits (sells); shown in red for net debit, blue for net credit. **Smart bot price**: same total logic but using mid (average of bid and ask) per leg.
- **Legs and quotes** – Legs are keyed by (expiration, strike, type). Bid/ask/delta are stored per leg and survive add/remove/edit and table sorting. Editing a cell (expiration, strike, type, action, mult) applies the same logic as the Edit button: merge if another row has the same key, otherwise replace and re-sort.
- **P&L at expiration** – The chart shows intrinsic value at expiry (no time value): for each underlying price on the x-axis, the y-axis is (intrinsic value of the position at that underlying) minus the cost basis (the lazy bot total). Requires the optional `PyQt6-Charts` package (`pip install PyQt6-Charts` in the project venv). If the package is missing, the P&L section is hidden.

## If prices don’t load

- Check the **red status bar** at the bottom: it shows the reason (e.g. connection lost, TWS not running, or the full error).
- **TWS or IB Gateway** must be running and the API enabled; if the status says “Connection lost” or “socket error”, click **Connect** (or **Load expirations**) to reconnect.
- If the status says “No quotes for these strikes/expirations”, the strike may not exist in the chain for the chosen expiration (e.g. wrong strike or expiration). Try a strike you see in your broker’s chain for that date.
- **Error 326 / “client id is already in use”**: TWS allows one connection per client ID. The app uses client ID 1 for expirations and 2 for quotes. If another app is using those IDs, set unique values in `.env`, e.g. `IBKR_CLIENT_ID=3` and `IBKR_CLIENT_ID_QUOTES=4`.
- Details are also written to `logs/position_builder/connection.log`.

## Running tests (no UI)

From project root:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\pytest tests/test_position_pricing.py tests/test_builder_service.py -v
```

All position and builder-service tests should pass. Other tests may require extra dependencies (e.g. `pyodbc`, `python-dotenv`).
