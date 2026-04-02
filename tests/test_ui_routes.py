from app.api.routes.ui import home, job_details_page


def test_home_returns_ui_shell() -> None:
    response = home()
    body = response.body.decode()

    assert response.status_code == 200
    assert '<script src="/static/ui.js" defer></script>' in body
    assert 'id="app"' in body
    assert "Stored jobs" in body


def test_job_details_page_returns_ui_shell() -> None:
    response = job_details_page(job_id=12)
    body = response.body.decode()

    assert response.status_code == 200
    assert 'data-route="job:12"' in body
    assert "Job #12" in body
