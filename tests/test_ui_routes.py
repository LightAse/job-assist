from app.api.routes.ui import (
    candidate_profile_page,
    home,
    job_details_page,
    profile_builder_page,
    resume_profiles_page,
    settings_page,
)


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


def test_resume_profiles_page_returns_ui_shell() -> None:
    response = resume_profiles_page()
    body = response.body.decode()

    assert response.status_code == 200
    assert 'data-route="profile-builder"' in body
    assert "Profile Builder" in body


def test_candidate_profile_page_returns_ui_shell() -> None:
    response = candidate_profile_page()
    body = response.body.decode()

    assert response.status_code == 200
    assert 'data-route="candidate-data"' in body
    assert "Candidate Data" in body


def test_profile_builder_page_returns_ui_shell() -> None:
    response = profile_builder_page()
    body = response.body.decode()

    assert response.status_code == 200
    assert 'data-route="profile-builder"' in body
    assert "Profile Builder" in body


def test_settings_page_returns_ui_shell() -> None:
    response = settings_page()
    body = response.body.decode()

    assert response.status_code == 200
    assert 'data-route="settings"' in body
    assert "Settings" in body
