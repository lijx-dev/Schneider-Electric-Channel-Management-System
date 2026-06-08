# Production MySQL Release Checklist

## Policy

Schema changes for the production database must be applied only through Alembic migrations.

The release order is fixed: run `alembic upgrade head` first, then start or roll out the application container.

Application startup now verifies database connectivity and the Alembic head revision only. It no longer runs `create_all`, and it no longer auto-adds columns.

The Docker image must ship with `app/`, `migrations/`, and `alembic.ini` so that the migration job and the app container use the same artifact.

## Required Environment

Make sure `faq-backend/.env` or the equivalent production environment contains at least:

```ini
ENVIRONMENT=production
DB_TYPE=mysql
DATABASE_URL=mysql+aiomysql://<user>:<password>@<host>:<port>/<database>
SECRET_KEY=<strong-random-secret>
STORAGE_BACKEND=cos
COS_SECRET_ID=<secret-id>
COS_SECRET_KEY=<secret-key>
COS_REGION=<region>
COS_BUCKET=<bucket>
```

Back up the production database before running migrations.

## Standard Release Flow

Build the release image:

```powershell
cd D:\project\分销系统\分销系统\faq-backend
docker build -t faq-backend:release .
```

Check the current migration revision with the new image:

```powershell
docker run --rm --env-file .env faq-backend:release `
  python -m alembic -c alembic.ini current
```

Apply the released migrations with the new image:

```powershell
docker run --rm --env-file .env faq-backend:release `
  python -m alembic -c alembic.ini upgrade head
```

Confirm the database is now at head:

```powershell
docker run --rm --env-file .env faq-backend:release `
  python -m alembic -c alembic.ini current
```

Expected output should include the current release head, for example:

```text
20260330_01 (head)
```

Start or update the application container only after migration succeeds:

```powershell
docker run -d --name faq-backend `
  --env-file .env `
  -p 8000:8000 `
  faq-backend:release
```

If the production platform is Kubernetes, TKE, or another orchestrator, keep the same sequence. Run a one-off migration job with the new image first. Update the application Deployment only after the migration job succeeds. Do not put migrations into the app startup command.

## Post-Release Checks

Verify `GET /health`.

Verify the main quiz flows, duplicate submission blocking, and score accumulation.

Check logs for connection errors or Alembic revision mismatch errors.

## Equivalent Host-Side Migration Command

If your platform requires migrations to run outside the container, keep the same order and run:

```powershell
cd D:\project\分销系统\分销系统\faq-backend
.\venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
```

Start the application only after the migration step finishes successfully.
