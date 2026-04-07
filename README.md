# Job Assist

## Docker Deployment

This project is set up for a simple two-container deployment:

- `frontend`: nginx reverse proxy for the browser UI
- `backend`: FastAPI app and SQLite persistence

The backend still serves the UI and API. The frontend container exists to give you a clean public entrypoint on your server while keeping the backend directly reachable for the browser extension over Tailscale.

### Ports

- Frontend UI: `${FRONTEND_PORT:-8080}`
- Backend API: `${BACKEND_PORT:-8000}`

Typical Tailscale access from your PC:

- UI: `http://<tailscale-server-ip>:8080`
- API/plugin target: `http://<tailscale-server-ip>:8000`

### Environment

Create a `.env` file on the server before starting the stack:

```bash
cp .env.example .env
```

Important values:

- `BACKEND_PORT`: host port for the FastAPI backend
- `FRONTEND_PORT`: host port for the nginx frontend
- `JOB_ASSIST_CORS_ALLOWED_ORIGINS`: comma-separated UI origins allowed to call the backend
- `JOB_ASSIST_CORS_ALLOWED_ORIGIN_REGEX`: regex for extension origins, default `chrome-extension://.*`
- `JOB_ASSIST_DB_PATH`: set automatically in Docker to `/app/data/job_assist.db`

Example for a Tailscale deployment:

```env
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_PORT=8080
JOB_ASSIST_CORS_ALLOWED_ORIGINS=http://100.101.102.103:8080
JOB_ASSIST_CORS_ALLOWED_ORIGIN_REGEX=chrome-extension://.*
```

If you use OpenRouter or other provider settings, add those values in `.env` as well.

### How Frontend Reaches Backend

The `frontend` container uses nginx to proxy all requests to `backend:8000` over the internal Docker network. That means:

- the page UI is opened through the frontend port
- the UI keeps using relative URLs
- no frontend build step or separate API URL injection is required

### Browser Extension Setup

The extension popup now includes a `Backend URL` field. On your PC, set it to your server's Tailscale backend address, for example:

```text
http://100.101.102.103:8000
```

Then click `Save URL`.

The extension stores that value in browser extension storage and uses it for `/plugins/scrape-current`.

### Start / Restart

From the project directory on the server:

```bash
docker compose up -d --build
```

To update after pulling changes:

```bash
git pull
docker compose up -d --build
```

To stop the stack:

```bash
docker compose down
```

### Persistence

SQLite data and generated CV artifacts are stored in the named Docker volume `job_assist_data`, mounted at `/app/data` inside the backend container.
