from abc import ABC, abstractmethod

from app.schemas.scrape import ScrapeCurrentRequest, ScrapeCurrentResponse


class JobScraperPlugin(ABC):
    plugin_name: str

    @abstractmethod
    def matches(self, payload: ScrapeCurrentRequest) -> bool:
        """Return True when this plugin can handle the input."""

    @abstractmethod
    def scrape(self, payload: ScrapeCurrentRequest) -> ScrapeCurrentResponse:
        """Return the current scrape result for the input."""
