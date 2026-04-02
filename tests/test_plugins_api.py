from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_scrape_current_returns_linkedin_plugin_response() -> None:
    response = client.post(
        "/plugins/scrape-current",
        json={
            "url": "https://www.linkedin.com/jobs/view/1234567890/",
            "title": "Senior Backend Engineer",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "plugin_name": "linkedin_job_scraper",
        "matched": True,
        "source_url": "https://www.linkedin.com/jobs/view/1234567890/",
        "raw_content": None,
        "structured_data": {
            "external_job_id": "1234567890",
            "page_title": "Senior Backend Engineer",
            "source": "linkedin",
        },
    }


def test_scrape_current_returns_404_for_non_matching_url() -> None:
    response = client.post(
        "/plugins/scrape-current",
        json={
            "url": "https://example.com/jobs/1234567890",
            "title": "Example role",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "No scraper plugin matched the provided input.",
    }


def test_scrape_current_accepts_html_and_visible_text_context() -> None:
    response = client.post(
        "/plugins/scrape-current",
        json={
            "url": "https://www.linkedin.com/jobs/view/1234567890/",
            "html": "<html><body><h1>Senior Backend Engineer</h1></body></html>",
            "visible_text": "Senior Backend Engineer at Example Co",
        },
    )

    assert response.status_code == 200
    assert response.json()["plugin_name"] == "linkedin_job_scraper"
    assert response.json()["structured_data"] == {
        "external_job_id": "1234567890",
        "source": "linkedin",
        "tentative_job_title": "Senior Backend Engineer",
    }
