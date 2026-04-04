from collections.abc import Iterable

from app.plugins.base import JobScraperPlugin
from app.plugins.generic_job_capture import GenericJobCapturePlugin
from app.plugins.linkedin_job_scraper import LinkedInJobScraperPlugin
from app.schemas.scrape import ScrapeContext


class PluginRegistry:
    def __init__(self, plugins: Iterable[JobScraperPlugin]) -> None:
        self._plugins = list(plugins)

    def get_first_match(self, context: ScrapeContext) -> JobScraperPlugin | None:
        for plugin in self._plugins:
            if plugin.matches(context):
                return plugin
        return None


plugin_registry = PluginRegistry(
    plugins=[
        LinkedInJobScraperPlugin(),
        GenericJobCapturePlugin(),
    ]
)
