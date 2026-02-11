# SPX Options – Query Bot

Automation for querying and storing SPX options chain data (read-only) from Interactive Brokers, with SQL Server Express storage and a simple UI.

## Overview

- **Data**: SPX options chains (bid/ask/last) at 1‑minute frequency.
- **Storage**: SQL Server Express. One table per underlying (e.g. `option_snapshots_SPX`).
- **UI**: Pick expiration, option kind (call/put), strike; view option price vs time in a chart.
- **Suppliers**: Pluggable interface (e.g. IBKR); read-only access with security logging.

**Two ways to run:**

1. **Collector (bot)** – Connects to IBKR (TWS or Gateway), fetches the options chain every minute, and writes snapshots to the database. Run this and leave it running to build history.
2. **UI** – Reads from the database so you can select an expiration, call/put, strike and see bid/ask/last vs time. Use this after the collector has stored some data.

---

## Setup

All commands below are for **PowerShell** from the project root (the `SPX_Options` folder).

### 1. Virtual environment and dependencies

```powershell
cd "E:\My Documents\Document Scans\Irina\Money\Interactive Brokers\2026.02.11 - Query Bot\SPX_Options"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

(Adjust the `cd` path to your actual project location.)

### 2. Configuration (`.env`)

Copy the example env file and edit it with your settings:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set at least:

- **SQL_CONNECTION_STRING** – Connection to your SQL Server and database (see [Database](#database) below).
- **IBKR_HOST** / **IBKR_PORT** – Only if you need to override defaults. Defaults: `127.0.0.1` and `7497` (TWS paper). Use `7496` for TWS live; use `4002` / `4001` if you use IB Gateway instead of the desktop app.
- **IBKR_USERNAME** / **IBKR_PASSWORD** – Optional; required only if your TWS/Gateway is set up to require API login.

Never commit `.env`; it is listed in `.gitignore` and `.cursorignore`.

### 3. Database

**Database name:** The app uses a single database, default name **OptionData** (set `SQL_DATABASE` or use `DATABASE=...` in your connection string). Inside it we create **one table per ticker** (e.g. `option_snapshots_SPX`).

**Auto-create:** If the database does not exist, the app will connect to `master`, create it, then retry. You only need to ensure the SQL Server login can create databases (or create the database yourself once).

1. Ensure **SQL Server Express** is running.

2. **Use a SQL login** (recommended). In SSMS or `sqlcmd`:

   ```sql
   USE master;
   CREATE LOGIN spxbot WITH PASSWORD = 'YourStrongPassword1!';
   -- Option A: let the app create the database on first run (login needs dbcreator or create OptionData manually once)
   CREATE DATABASE OptionData;
   USE OptionData;
   CREATE USER spxbot FOR LOGIN spxbot;
   ALTER ROLE db_datareader ADD MEMBER spxbot;
   ALTER ROLE db_datawriter ADD MEMBER spxbot;
   ALTER ROLE db_ddladmin ADD MEMBER spxbot;
   ```

   Or create `OptionData` yourself; the app will create tables inside it on first run.

3. In `.env`, set the connection string (no `Trusted_Connection` if using SQL login):

   ```
   SQL_CONNECTION_STRING=DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLEXPRESS;DATABASE=OptionData;UID=spxbot;PWD=YourStrongPassword1!;
   ```

   If the database does not exist, the app will try to create it (requires login with permission to create databases, or create `OptionData` manually first).

The app creates tables automatically on first run (e.g. `option_snapshots_SPX`). SQL Server Express (up to 10 GB per database) is enough for this use case.

### 4. IBKR (TWS or Gateway)

- Run **IBKR desktop (TWS)** or **IB Gateway** and log in (paper or live).
- In TWS: **Edit → Global Configuration → API → Settings**:
  - Enable **Enable ActiveX and Socket Clients**.
  - Note the **Socket port** (TWS paper `7497`, live `7496`; Gateway paper `4002`, live `4001`).
- The collector connects to `127.0.0.1` and that port. No need to set host/port in `.env` if you use defaults (TWS paper = 7497).

---

## Running

Commands are from the **project root** with the venv activated (run `.venv\Scripts\Activate.ps1` if needed).

### Option A: PowerShell scripts (no extra install)

These scripts set `PYTHONPATH` so the `spx_options` package is found without `pip install -e .`:

**Start the collector (bot):**

```powershell
.\run_collector.ps1
```

Leave this running. It will connect to TWS/Gateway and store a chain snapshot every 60 seconds.

**Start the UI:**

```powershell
.\run_ui.ps1
```

Use the UI to choose expiration, call/put, strike and view price vs time (after the collector has written some data).

### Option B: Install package and use Python directly

Install the package in editable mode once:

```powershell
pip install -e .
```

Then run:

```powershell
# Collector (bot)
python -m spx_options.collector_main

# UI (in another terminal)
python -m spx_options.ui.main
```

### Tests

```powershell
pytest tests\ -v
```

Repository and collector tests need a working SQL Server connection; they are skipped if the database is unavailable.

---

## Configuration reference

| Variable | Description | Default |
|----------|-------------|---------|
| `IBKR_USERNAME` | IBKR API username | (empty) |
| `IBKR_PASSWORD` | IBKR API password | (empty) |
| `IBKR_HOST` | TWS/Gateway host | `127.0.0.1` |
| `IBKR_PORT` | TWS/Gateway port; TWS paper=7497, live=7496; Gateway paper=4002, live=4001 | `7497` |
| `SQL_CONNECTION_STRING` | ODBC connection string to SQL Server and database | (see `.env.example`) |

---

## Project layout

- **`src/spx_options/`** – Main package:
  - `config.py` – Loads settings from `.env`.
  - `security_log.py` – Security logging for IBKR access.
  - `suppliers/` – Pluggable data sources (e.g. `ibkr.py` for Interactive Brokers).
  - `db/` – SQL Server connection, schema, repository (insert/query snapshots).
  - `collector.py` – 1‑minute loop: fetch chain, insert into DB.
  - `collector_main.py` – Entry point for the collector.
  - `ui/main.py` – PyQt6 UI: expiration, kind, strike, price vs time chart.
- **`run_collector.ps1`** – PowerShell launcher for the collector (sets `PYTHONPATH`, runs collector).
- **`run_ui.ps1`** – PowerShell launcher for the UI.
- **`tests/`** – Unit tests (suppliers, repository, collector, .gitignore).

---

## License

Private use.
