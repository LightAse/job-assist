from collections.abc import Iterable

from app.plugins.base import JobScraperPlugin
from app.plugins.linkedin_job_scraper import LinkedInJobScraperPlugin
from app.schemas.scrape import ScrapeCurrentRequest


class PluginRegistry:
    def __init__(self, plugins: Iterable[JobScraperPlugin]) -> None:
        self._plugins = list(plugins)

    def get_first_match(self, payload: ScrapeCurrentRequest) -> JobScraperPlugin | None:
        for plugin in self._plugins:
            if plugin.matches(payload):
                return plugin
        return None


plugin_registry = PluginRegistry(
    plugins=[
        LinkedInJobScraperPlugin(),
    ]
)
