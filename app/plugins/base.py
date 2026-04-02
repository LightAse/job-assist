from abc import ABC, abstractmethod

from app.schemas.scrape import ScrapeContext, ScrapeCurrentResponse


class JobScraperPlugin(ABC):
    plugin_name: str

    @abstractmethod
    def matches(self, context: ScrapeContext) -> bool:
        """Return True when this plugin can handle the input."""

    @abstractmethod
    def scrape(self, context: ScrapeContext) -> ScrapeCurrentResponse:
        """Return the current scrape result for the input."""
