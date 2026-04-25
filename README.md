# Job Assist

This project is still in active development. Expect rough edges, missing polish, and changes to setup or behavior as features are still being built out.

Job Assist is a small FastAPI app for saving job posts, reviewing them in a browser UI, and generating resume-related outputs from your own candidate data.

It has three main pieces:

- A FastAPI backend with a built-in web UI
- A SQLite database for saved jobs, profiles, settings, and generated CVs
- A Chrome extension that captures the current job page and sends it to the backend

## What It Can Do

- Save job posts from LinkedIn and generic job pages
- Deduplicate repeated captures of the same posting
- Show saved jobs in a built-in UI
- Store candidate info, skills, work history, projects, education, certifications, languages, and links
- Build resume profiles from that data
- Run compatibility scoring
- Generate a job-specific CV artifact

## Project Layout

- `app/`: FastAPI app, routes, services, persistence, static UI
- `browser-extension/`: Chrome extension used to capture job pages
- `tests/`: pytest coverage for API routes, persistence, services, and UI routes
- `docker-compose.yml`: two-container deployment

## Quick Start

### Option 1: Run Locally

Requirements:

- Python 3.11+

Install and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
set -a && source .env && set +a
uvicorn backend:app --reload --host 127.0.0.1 --port 8000
```

Open:

- UI: `http://127.0.0.1:8000/`
- FastAPI docs: `http://127.0.0.1:8000/docs`

Default local database path:

- `data/job_assist.db`

### Option 2: Run With Docker

Create your env file:

```bash
cp .env.example .env
```

Start the stack:

```bash
docker compose up -d --build
```

Open:

- UI through nginx: `http://127.0.0.1:8080/`
- Backend API directly: `http://127.0.0.1:8000/`

Stop:

```bash
docker compose down
```

Docker uses a named volume called `job_assist_data` and stores the SQLite DB at `/app/data/job_assist.db` inside the backend container.

## Environment Variables

The repo includes [.env.example](/home/ianf/server-projects/job-assist/.env.example).

Most important values:

- `BACKEND_HOST`: backend bind host
- `BACKEND_PORT`: host port mapped to the backend container
- `FRONTEND_PORT`: host port mapped to nginx
- `JOB_ASSIST_CORS_ALLOWED_ORIGINS`: comma-separated allowed UI origins
- `JOB_ASSIST_CORS_ALLOWED_ORIGIN_REGEX`: allowed regex for Chrome and Firefox extension origins
- `JOB_ASSIST_DB_PATH`: SQLite path when not using Docker
- `COMPATIBILITY_PROVIDER`: `deterministic`, `openrouter`, or `opencode`
- `OPENROUTER_API_KEY`: API key if you use an OpenRouter-backed provider
- `OPENROUTER_MODEL`: default model id
- `OPENROUTER_BASE_URL`: base URL for the model endpoint

Minimal local example:

```env
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_PORT=8080
JOB_ASSIST_CORS_ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:8080,http://localhost:8080
JOB_ASSIST_CORS_ALLOWED_ORIGIN_REGEX='^(chrome-extension|moz-extension):\/\/.*$'
JOB_ASSIST_DB_PATH=data/job_assist.db

COMPATIBILITY_PROVIDER=deterministic
OPENROUTER_MODEL=openrouter/gpt-5-nano
OPENROUTER_TIMEOUT_SECONDS=20
```

`deterministic` is the easiest way to start because it does not require a live model provider for the resume-profile compatibility scoring route.

## Using the App

Recommended flow:

1. Start the backend.
2. Open the UI and confirm it loads.
3. Load the extension from `browser-extension/` in Chrome developer mode.
4. In the extension popup, set `Backend URL` to your backend, for example `http://127.0.0.1:8000`.
5. Visit a supported job page and capture it.
6. Open the UI to review saved jobs.
7. Fill in candidate data and resume data.
8. Create a resume profile if you want profile-based scoring.
9. Run compatibility checks or generate a CV.

## Browser Extension

The extension lives in `browser-extension/`.

To load it in Chrome:

1. Go to `chrome://extensions`
2. Enable Developer Mode
3. Click `Load unpacked`
4. Select the `browser-extension/` folder

In the popup, set `Backend URL` to the backend directly, not the nginx frontend. Example:

```text
http://127.0.0.1:8000
```

The extension sends captures to:

- `POST /plugins/scrape-current`

## Main Routes

UI pages:

- `GET /`
- `GET /jobs/{job_id}/view`
- `GET /candidate-profile/view`
- `GET /profile-builder/view`
- `GET /settings/view`

Jobs:

- `GET /jobs`
- `GET /jobs/{job_id}`
- `PUT /jobs/{job_id}/status`
- `POST /jobs/{job_id}/compatibility-checks`
- `POST /jobs/{job_id}/candidate-compatibility-check`
- `POST /jobs/{job_id}/generate-cv`
- `GET /jobs/generated-cvs/{artifact_id}/download`
- `DELETE /jobs/{job_id}`

Capture:

- `POST /plugins/scrape-current`

Candidate and resume data:

- `GET /candidate-profile`
- `PUT /candidate-profile`
- `GET /resume-profiles`
- `POST /resume-profiles`
- `GET /resume-profiles/workspace`
- `POST /resume-import/parse`
- `POST /resume-import/confirm`

Settings:

- `GET /settings/openrouter`
- `PUT /settings/openrouter`
- `GET /settings/models`
- `POST /settings/models/refresh`
- `GET /settings/prompts`
- `PUT /settings/prompts`

## Example JSON Responses

### Example: `POST /plugins/scrape-current`

Request:

```json
{
  "url": "https://www.linkedin.com/jobs/view/1234567890/",
  "title": "Senior Backend Engineer",
  "company": "Example Co",
  "location": "Remote",
  "visible_text": "Senior Backend Engineer at Example Co",
  "linkedin_job_id": "1234567890"
}
```

Typical response:

```json
{
  "plugin_name": "linkedin_job_scraper",
  "matched": true,
  "source_url": "https://www.linkedin.com/jobs/view/1234567890/",
  "raw_content": null,
  "structured_data": {
    "external_job_id": "1234567890",
    "page_title": "Senior Backend Engineer",
    "source": "linkedin"
  },
  "status": "created",
  "job_id": 1,
  "deduplicated": false,
  "reason": null
}
```

If the same job is captured again, the response can come back as a deduplicated skip:

```json
{
  "plugin_name": "linkedin_job_scraper",
  "matched": true,
  "source_url": "https://www.linkedin.com/jobs/view/1234567890/",
  "raw_content": null,
  "structured_data": {
    "external_job_id": "1234567890",
    "page_title": "Senior Backend Engineer",
    "source": "linkedin"
  },
  "status": "skipped",
  "job_id": 1,
  "deduplicated": true,
  "reason": "duplicate"
}
```

### Example: `GET /jobs/1`

Example response:

```json
{
  "id": 1,
  "source": "linkedin",
  "external_job_id": "1234567890",
  "source_url": "https://www.linkedin.com/jobs/view/1234567890/",
  "page_title": "Senior Backend Engineer",
  "tentative_job_title": "Senior Backend Engineer",
  "status": "new",
  "created_at": "2026-04-13T12:00:00+00:00",
  "latest_snapshot": {
    "id": 1,
    "title": "Senior Backend Engineer",
    "company": "Example Co",
    "location": "Remote",
    "visible_text": "Senior Backend Engineer at Example Co",
    "html": null,
    "plugin_name": "linkedin_job_scraper",
    "captured_at": "2026-04-13T12:00:00+00:00"
  },
  "latest_compatibility_check": null,
  "latest_candidate_compatibility_check": null,
  "generated_cvs": []
}
```

## Running Tests

```bash
pytest
```

## Notes

- The backend itself serves the UI. The frontend container is only a reverse proxy.
- The browser extension should target the backend API directly.
- Generated CV files are stored next to the SQLite DB in a `generated_cvs/` directory.
