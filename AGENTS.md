# Securo contributor guide

## Repository layout

- `backend/` is the FastAPI application, SQLAlchemy models/services, and Alembic migrations.
- `frontend/` is the Vite + React + TypeScript application.
- `docker-compose.yml` and `docker-compose.prod.yml` define local and production-style stacks.
- `backend/scripts/` contains explicit, repeatable seed and maintenance scripts. They must never read or commit production exports.

## Backend conventions

- Keep API routes thin; put business rules in `backend/app/services/`.
- Scope every query and mutation by workspace (and user where applicable).
- Add an Alembic migration for every schema change. Migrations must be transactional where PostgreSQL supports it and must preserve historical references.
- Use Pydantic schemas for request/response validation and return clear `400`/`404` errors from routes.
- Run `python3 -m compileall -q backend/app backend/alembic/versions/<migration>.py` before committing Python changes.

## Frontend conventions

- Use shared components from `frontend/src/components/ui/` for inputs, labels, dialogs, selects, and buttons.
- Use `CurrencySelect` for currency fields; do not replace it with free-text currency inputs.
- Keep user-facing strings in `frontend/src/locales/` and use `useTranslation()`.
- Use React Query API wrappers in `frontend/src/lib/api.ts` rather than calling Axios directly from pages.
- Preserve keyboard focus, labels, and mobile layouts when changing forms.

## Data and migration safety

- Never commit `.env` files, database dumps, credentials, tokens, account numbers, transaction exports, or personal financial records.
- Taxonomy migrations are deterministic, tenant-scoped population/normalization steps: embed only canonical labels and mapping rules; generate IDs and timestamps at runtime.
- Before applying a production data migration, create a timestamped backup and validate counts, totals, and restoreability.
- Prefer reversible archive/merge operations over destructive deletes; record audit mappings when moving historical references.

## Verification and deployment

- Frontend production check: `docker build -f frontend/Dockerfile -t local/securo-frontend:try-v0.14.5 frontend`.
- Backend/stack check: `docker compose -f /home/manager/apps/securo/docker-compose.yml up -d --force-recreate backend frontend celery-worker celery-beat`.
- Verify Alembic head, `GET /api/health`, and the frontend HTTP response after deployment.
- Commit focused changes with descriptive messages and review `git diff --stat` plus tracked-file secret checks before pushing.
