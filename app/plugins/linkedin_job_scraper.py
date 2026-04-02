from urllib.parse import urlparse

from app.plugins.base import JobScraperPlugin
from app.schemas.scrape import ScrapeContext, ScrapeCurrentResponse


class LinkedInJobScraperPlugin(JobScraperPlugin):
    plugin_name = "linkedin_job_scraper"
    _supported_hosts = {"www.linkedin.com", "linkedin.com"}
    _title_separators = (" at ", " - ", " | ")

    def matches(self, context: ScrapeContext) -> bool:
        parsed = urlparse(str(context.url))
        return parsed.scheme in {"http", "https"} and parsed.netloc in self._supported_hosts and "/jobs/view/" in parsed.path

    def scrape(self, context: ScrapeContext) -> ScrapeCurrentResponse:
        structured_data = {
            "external_job_id": self._extract_job_id(str(context.url)),
            "source": "linkedin",
        }
        if context.title:
            structured_data["page_title"] = context.title
        tentative_job_title = self._extract_tentative_job_title(context.visible_text)
        if tentative_job_title:
            structured_data["tentative_job_title"] = tentative_job_title

        return ScrapeCurrentResponse(
            plugin_name=self.plugin_name,
            matched=True,
            source_url=context.url,
            raw_content=None,
            structured_data=structured_data,
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

    @classmethod
    def _extract_tentative_job_title(cls, visible_text: str | None) -> str | None:
        if not visible_text:
            return None

        first_line = next((line.strip() for line in visible_text.splitlines() if line.strip()), "")
        if not first_line:
            return None

        for separator in cls._title_separators:
            if separator in first_line:
                candidate = first_line.split(separator, 1)[0].strip()
                return candidate or None

        return first_line
