from app.plugins.registry import plugin_registry
from app.schemas.scrape import ScrapeCurrentRequest


def test_plugin_registry_matches_linkedin_job_url() -> None:
    payload = ScrapeCurrentRequest(
        url="https://www.linkedin.com/jobs/view/1234567890/",
        title="Backend Engineer",
    )

    plugin = plugin_registry.get_first_match(payload)

    assert plugin is not None
    assert plugin.plugin_name == "linkedin_job_scraper"


def test_plugin_registry_returns_none_for_non_matching_url() -> None:
    payload = ScrapeCurrentRequest(
        url="https://example.com/jobs/1234567890",
        visible_text="Example listing",
    )

    plugin = plugin_registry.get_first_match(payload)

    assert plugin is not None
    assert plugin.plugin_name == "generic_job_capture"
