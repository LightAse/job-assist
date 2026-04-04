from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["ui"])


def _render_ui_shell(*, title: str, page_heading: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="stylesheet" href="/static/ui.css">
  </head>
  <body>
    <main class="page">
      <header class="page-header">
        <div>
          <p class="eyebrow">Job Assist</p>
          <h1>{page_heading}</h1>
        </div>
        <div class="header-actions">
          <nav class="nav-links" aria-label="Primary">
            <a class="button button-secondary" href="/">Jobs</a>
            <a class="button button-secondary" href="/candidate-profile/view">Candidate Data</a>
            <a class="button button-secondary" href="/profile-builder/view">Profile Builder</a>
            <a class="button button-secondary" href="/settings/view">Settings</a>
          </nav>
          <button id="check-all-button" class="button button-secondary">Check All</button>
          <button id="check-unscored-button" class="button button-secondary" hidden>Check Unscored</button>
        </div>
      </header>
      <section id="message" class="message" hidden></section>
      <section id="app" class="panel" data-route="{title}">
        <p class="muted">Loading...</p>
      </section>
    </main>
    <script src="/static/ui.js" defer></script>
  </body>
</html>"""
    )


@router.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return _render_ui_shell(title="jobs", page_heading="Stored jobs")


@router.get("/jobs/{job_id}/view", response_class=HTMLResponse)
def job_details_page(job_id: int) -> HTMLResponse:
    return _render_ui_shell(title=f"job:{job_id}", page_heading=f"Job #{job_id}")


@router.get("/resume-profiles/view", response_class=HTMLResponse)
def resume_profiles_page() -> HTMLResponse:
    return _render_ui_shell(title="profile-builder", page_heading="Profile Builder")


@router.get("/candidate-profile/view", response_class=HTMLResponse)
def candidate_profile_page() -> HTMLResponse:
    return _render_ui_shell(title="candidate-data", page_heading="Candidate Data")


@router.get("/profile-builder/view", response_class=HTMLResponse)
def profile_builder_page() -> HTMLResponse:
    return _render_ui_shell(title="profile-builder", page_heading="Profile Builder")


@router.get("/settings/view", response_class=HTMLResponse)
def settings_page() -> HTMLResponse:
    return _render_ui_shell(title="settings", page_heading="Settings")
