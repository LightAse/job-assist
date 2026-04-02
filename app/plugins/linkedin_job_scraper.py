from urllib.parse import urlparse

from app.plugins.base import JobScraperPlugin
from app.schemas.scrape import ScrapeContext, ScrapeCurrentResponse


class LinkedInJobScraperPlugin(JobScraperPlugin):
    plugin_name = "linkedin_job_scraper"
    _supported_hosts = {"www.linkedin.com", "linkedin.com"}

    def matches(self, context: ScrapeContext) -> bool:
        parsed = urlparse(str(context.url))
        return parsed.scheme in {"http", "https"} and parsed.netloc in self._supported_hosts and "/jobs/view/" in parsed.path

    def scrape(self, context: ScrapeContext) -> ScrapeCurrentResponse:
        return ScrapeCurrentResponse(
            plugin_name=self.plugin_name,
            matched=True,
            source_url=context.url,
            raw_content=None,
            structured_data={
                "external_job_id": self._extract_job_id(str(context.url)),
                "source": "linkedin",
            },
        )

    @staticmethod
    def _extract_job_id(url: str) -> str | None:
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        try:
            view_index = path_parts.index("view")
        except ValueError:
            return None
        next_index = view_index + 1
        if next_index >= len(path_parts):
            return None
        return path_parts[next_index]
