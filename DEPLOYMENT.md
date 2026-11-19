# Deployment Guide

This project can run locally with Flask, but production deployment should use `waitress` behind a reverse proxy such as Caddy or Nginx.

## 1. Environment

Create a production `.env` based on [.env.example](./.env.example).

Minimum required values:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=zambia_climate_portal
DB_USER=postgres
DB_PASSWORD=replace-with-your-db-password

SECRET_KEY=replace-with-a-long-random-secret
APP_DEBUG=False
API_KEY=replace-with-a-long-random-api-key
ADMIN_TOKEN=replace-with-a-long-random-admin-token
```

Optional logging controls:

```env
LOG_FILE=logs/app.log
LOG_MAX_BYTES=2097152
LOG_BACKUP_COUNT=5
```

## 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

## 3. Run the App

Production-style app server:

```powershell
python -m waitress --host=127.0.0.1 --port=5000 backend.app:app
```

Or use the included helper:

```powershell
.\run_prod.bat
```

## 4. Reverse Proxy

Use one of the templates in [deploy](./deploy):

- [deploy/Caddyfile](./deploy/Caddyfile)
- [deploy/nginx.conf](./deploy/nginx.conf)

These should terminate HTTPS and proxy requests to `127.0.0.1:5000`.

## 5. Health Check

Verify the app is healthy after startup:

```powershell
curl http://127.0.0.1:5000/api/v1/health
```

Expected:

- HTTP `200`
- JSON body with `"status": "healthy"`

## 6. Logging

The app now uses rotating logs by default:

- active log: `logs/app.log`
- rotated backups: `logs/app.log.1`, `logs/app.log.2`, etc.

Defaults:

- max file size: 2 MB
- backups kept: 5

These can be changed with `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`.

## 7. Production Checklist

- `APP_DEBUG=False`
- `SECRET_KEY`, `API_KEY`, `ADMIN_TOKEN` all set
- PostgreSQL reachable with the configured credentials
- reverse proxy configured for HTTPS
- firewall only exposes `80/443`
- app server bound behind proxy
- health endpoint checked after deploy
- database backups enabled

## 8. Windows Notes

For Windows hosting, you can run `waitress`:

- with Task Scheduler
- with NSSM
- as a Windows service wrapper

Point the service command to:

```powershell
python -m waitress --host=127.0.0.1 --port=5000 backend.app:app
```

## 9. Linux Notes

Typical Linux production stack:

- `waitress` as the app server
- `systemd` to keep the process alive
- Caddy or Nginx as reverse proxy

You can adapt the reverse-proxy templates in [deploy](./deploy) for your host and domain.
