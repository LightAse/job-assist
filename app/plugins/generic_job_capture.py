from urllib.parse import urlparse

from app.plugins.base import JobScraperPlugin
from app.schemas.scrape import ScrapeContext, ScrapeCurrentResponse


class GenericJobCapturePlugin(JobScraperPlugin):
    plugin_name = "generic_job_capture"
    _source_markers = (
        ("linkedin", ("linkedin.com",)),
        ("greenhouse", ("greenhouse.io",)),
        ("lever", ("lever.co",)),
        ("workday", ("myworkdayjobs.com", "workday.com")),
    )
    _title_separators = (" at ", " | ", " - ")

    def matches(self, context: ScrapeContext) -> bool:
        parsed = urlparse(str(context.url))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def scrape(self, context: ScrapeContext) -> ScrapeCurrentResponse:
        structured_data = {
            "source": self._detect_source(str(context.url)),
        }
        if context.title:
            structured_data["page_title"] = context.title

        tentative_job_title = self._extract_tentative_job_title(context)
        if tentative_job_title:
            structured_data["tentative_job_title"] = tentative_job_title

        external_job_id = context.linkedin_job_id or self._extract_external_job_id(str(context.url))
        if external_job_id:
            structured_data["external_job_id"] = external_job_id

        return ScrapeCurrentResponse(
            plugin_name=self.plugin_name,
            matched=True,
            source_url=context.url,
            raw_content=None,
            structured_data=structured_data,
        )

    @classmethod
    def _detect_source(cls, url: str) -> str:
        host = urlparse(url).netloc.lower()
        for source, markers in cls._source_markers:
            if any(marker in host for marker in markers):
                return source
        return "generic"

    @staticmethod
    def _extract_external_job_id(url: str) -> str | None:
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        for part in reversed(path_parts):
            digits = "".join(character for character in part if character.isdigit())
            if len(digits) >= 5:
                return digits
        return None

    @classmethod
    def _extract_tentative_job_title(cls, context: ScrapeContext) -> str | None:
        if context.visible_text:
            for line in context.visible_text.splitlines():
                candidate = cls._clean_title_candidate(line)
                if candidate:
                    return candidate

        return cls._clean_title_candidate(context.title)

    @classmethod
    def _clean_title_candidate(cls, value: str | None) -> str | None:
        if not value:
            return None

        candidate = " ".join(value.split())
        if not candidate:
            return None

        lowered = candidate.lower()
        for separator in cls._title_separators:
            separator_index = lowered.find(separator)
            if separator_index > 0:
                candidate = candidate[:separator_index].strip()
                break

        if len(candidate) < 3:
            return None

        return candidate
