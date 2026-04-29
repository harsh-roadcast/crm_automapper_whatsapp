# CRM Automapper WhatsApp

Python backend for a WhatsApp lead-qualification chatbot that maps completed and incomplete conversations into Zoho CRM.

## What is implemented

- FastAPI app bootstrap with health endpoints.
- Meta WhatsApp webhook verification and inbound message handling.
- Deterministic lead-qualification flow for:
	- welcome
	- name
	- fleet size
	- company name
	- work email
	- pain-point selection
	- closing message
- WhatsApp-safe interactive payload generation for list and button prompts.
- Lead persistence, conversation tracking, inbound message deduplication, and sync logs.
- Zoho Leads upsert service with WhatsApp-number based duplicate detection.
- 10-minute inactivity tracking with re-engagement task scheduling.
- Automated tests covering conversation flow, webhook orchestration, Zoho sync, and inactivity handling.

## Project structure

- `backend/app/main.py` builds the FastAPI application.
- `backend/app/api/routes/webhooks.py` exposes the Meta webhook endpoints.
- `backend/app/api/services/conversation_service.py` contains the qualification state machine.
- `backend/app/api/services/lead_workflow_service.py` persists conversations and lead progress.
- `backend/app/api/services/zoho_service.py` handles Zoho upsert logic.
- `backend/app/api/services/inactivity_service.py` handles the 10-minute incomplete-lead flow.
- `backend/app/api/tasks/reengagement_tasks.py` defines the Celery timeout task.

## Local setup

1. Install dependencies.

```bash
uv sync --group dev
```

2. Create local environment variables.

```bash
cp .env.example .env
```

3. Start PostgreSQL and Redis.

```bash
docker compose up -d postgres redis
```

4. Initialize database tables.

```bash
uv run python backend/scripts/init_db.py
```

5. Start the FastAPI app.

```bash
uv run python main.py
```

6. Start the Celery worker for inactivity re-engagement.

```bash
uv run celery -A backend.app.api.tasks.reengagement_tasks.celery_app worker --loglevel=info
```

## Helper scripts

You can use the top-level scripts directory instead of typing the commands manually.

1. Prepare local dependencies and initialize the database.

```bash
./scripts/setup_backend.sh
```

2. Run the FastAPI backend.

```bash
./scripts/run_backend.sh
```

3. Run the Celery worker for inactivity jobs.

```bash
./scripts/run_worker.sh
```

Optional environment overrides:

- `HOST=127.0.0.1 ./scripts/run_backend.sh`
- `PORT=9000 ./scripts/run_backend.sh`
- `RELOAD=0 ./scripts/run_backend.sh`
- `LOG_LEVEL=debug ./scripts/run_worker.sh`

## Environment variables

Required for the full integration:

- `POSTGRES_DSN`
- `REDIS_URL`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `ZOHO_CLIENT_ID`
- `ZOHO_CLIENT_SECRET`
- `ZOHO_REFRESH_TOKEN`

If Zoho credentials are not configured, the current implementation falls back to an offline sync mode that records a synthetic lead ID. This is useful for local testing but not for production.

## WhatsApp webhook setup

Use the following webhook URL in Meta:

- `GET /api/v1/webhooks/whatsapp` for verification
- `POST /api/v1/webhooks/whatsapp` for inbound messages

The verify token must match `WHATSAPP_VERIFY_TOKEN`.

## Qualification flow

The bot uses the WhatsApp sender number from session metadata and asks for:

1. Name
2. Fleet size
3. Company name
4. Work email
5. Pain points

Pain points are implemented as a sequential selection flow because standard WhatsApp interactive lists are single-select. Users can add multiple problems one by one.

## CRM behavior

- Completed flow: upsert the lead into Zoho Leads.
- Existing WhatsApp number: update instead of creating a duplicate.
- Incomplete flow after inactivity: mark as `Incomplete`, send re-engagement, and sync partial lead data.

## Tests

Run the backend test suite with:

```bash
uv run pytest backend/tests
```

## UAT checklist

- Verify Meta webhook challenge succeeds.
- Send an inbound WhatsApp message and confirm the welcome flow starts.
- Complete the questionnaire and confirm the Zoho lead is created or updated.
- Stop mid-flow for 10 minutes and confirm re-engagement plus incomplete sync.
- Replay the same webhook payload and confirm no duplicate processing.

## Next implementation targets

- Add Alembic migrations instead of using `create_all` for schema setup.
- Add outbound message logging for WhatsApp sends.
- Add signature verification for Meta webhook authenticity.
- Add Hindi flow support as phase 2.
