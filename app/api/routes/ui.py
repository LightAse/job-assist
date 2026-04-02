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
        <button id="check-all-button" class="button button-secondary">Check All</button>
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
