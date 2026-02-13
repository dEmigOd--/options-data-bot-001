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
2. **Load expirations** – Click to fetch expirations from IBKR (runs in background).
3. **Expiration list** – Select one expiration.
4. **Add leg** – Enter strike, choose Call/Put and Buy/Sell, then **Add leg**. Repeat for each leg.
5. **Legs table** – Shows Strike, Type, Action, **Bid**, **Ask** (filled after you have an expiration and legs and prices are refreshed).
6. **Lazy bot price** – Debit (red) or credit (blue): buy legs use ask, sell legs use bid; total = debits − credits.
7. **Smart bot price** – Same total logic using mid price per leg; red/blue for debit/credit.
8. **Refresh prices** – Manual refresh; a timer also refreshes every 15 seconds when you have an expiration and legs.

## Running tests (no UI)

From project root:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\pytest tests/test_position_pricing.py tests/test_builder_service.py -v
```

All position and builder-service tests should pass. Other tests may require extra dependencies (e.g. `pyodbc`, `python-dotenv`).
