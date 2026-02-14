# Commit plan

**Rule from now on:** After each logical change we prepare one commit. You review the suggested message and run the commit yourself (or approve and I don't run git).

---

## This branch: position-builder UI (suggested single commit)

You have many changed files on `feature/position-builder-ui` and no commits yet. Suggested **one commit** for the whole position-builder feature (you can split later if you prefer).

**Files to stage:**  
All modified + new: `docs/RUN_POSITION_BUILDER.md`, `README.md`, `requirements.txt`, `src/spx_options/config.py`, `src/spx_options/position/` (builder_service, leg, pricing, pnl_curve), `src/spx_options/suppliers/base.py`, `src/spx_options/suppliers/ibkr.py`, `src/spx_options/ui/position_builder.py`, `src/spx_options/ui/connection_log.py`, `tests/test_builder_service.py`, `tests/test_position_pricing.py`, `COMMITS.md`.

**Suggested message:** feat: Position Builder UI with legs, prices, P&L chart, two-column layout (full multi-line message in the command block below).

**Commands (run from project root):**

```powershell
git add docs/RUN_POSITION_BUILDER.md README.md requirements.txt COMMITS.md
git add src/spx_options/config.py src/spx_options/position/
git add src/spx_options/suppliers/base.py src/spx_options/suppliers/ibkr.py
git add src/spx_options/ui/position_builder.py src/spx_options/ui/connection_log.py
git add tests/test_builder_service.py tests/test_position_pricing.py
git commit -m "feat: Position Builder UI with legs, prices, P&L chart, two-column layout

- UI: ticker, expirations calendar, add/edit/remove legs, bid/ask/delta, lazy/smart bot price, P&L at expiry (PyQt6-Charts), scroll area, two-column layout (connection/calendar/P&L left; add leg/table/summary right)
- Position: builder_service, pnl_curve, leg, pricing; quotes keyed by (date, strike, type)
- IBKR: separate client IDs for expirations vs quotes, leg-only quotes, delta from Greeks, 5s refresh, add-leg triggers refresh
- Config: IBKR_CLIENT_ID, IBKR_CLIENT_ID_QUOTES
- Docs: README Position Builder section, RUN_POSITION_BUILDER how-to and how-it-works
- Tests: builder_service, position_pricing"
```

---

## Suggested chunks (if you're cleaning up one big blob)

Run these in order so history is readable. Adjust file lists to what you actually have uncommitted.

1. **docs: add database and SQL login setup**  
   - README (Database section), .env.example  
   - Message: `docs: document DB creation and SQL login for connection string`

2. **config and security**  
   - `src/spx_options/config.py`, `src/spx_options/security_log.py`  
   - Message: `feat: config from .env and security logging for IBKR`

3. **suppliers (pluggable + IBKR)**  
   - `src/spx_options/suppliers/` (base, ibkr, __init__)  
   - Message: `feat: pluggable options supplier and IBKR implementation`

4. **db (schema, connection, repository)**  
   - `src/spx_options/db/` (schema.sql, connection.py, repository.py, __init__)  
   - Message: `feat: SQL Server repo and table-per-underlying schema`

5. **collector**  
   - `src/spx_options/collector.py`, `src/spx_options/collector_main.py`  
   - Message: `feat: 1-minute collector loop and entry point`

6. **ui**  
   - `src/spx_options/ui/` (main.py, __init__)  
   - Message: `feat: PyQt6 UI for expiration/kind/strike and price vs time`

7. **tests**  
   - `tests/`  
   - Message: `test: suppliers, repository, collector, gitignore`

8. **scripts and project metadata**  
   - `run_collector.ps1`, `run_ui.ps1`, `pyproject.toml`, `requirements.txt`, `.gitignore`, `.cursorignore`  
   - Message: `chore: PowerShell launchers and project config`

9. **docs: README overview and run instructions**  
   - README (rest of changes)  
   - Message: `docs: README setup, run, and config reference`

---

## This session: commit for your review

**Suggested commit (database/login docs):**

- **Files:** `README.md`, `.env.example`, `COMMITS.md` (this file).
- **Message:**

```
docs: database setup and SQL login; add COMMITS.md

- README: one DB (any name), tables per ticker; create DB and SQL login (spxbot), set UID/PWD in .env
- .env.example: SQL_CONNECTION_STRING with UID/PWD and comment about DB name
- COMMITS.md: chunked commit plan and rule to review each commit message
```

Review the message; if it's good, stage and commit:

```powershell
git add README.md .env.example COMMITS.md
git commit -m "docs: database setup and SQL login; add COMMITS.md

- README: one DB (any name), tables per ticker; create DB and SQL login (spxbot), set UID/PWD in .env
- .env.example: SQL_CONNECTION_STRING with UID/PWD and comment about DB name
- COMMITS.md: chunked commit plan and rule to review each commit message"
```
