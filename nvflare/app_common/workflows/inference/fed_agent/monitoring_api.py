from abc import ABC, abstractmethod


class MonitoringAPI(ABC):
    @abstractmethod
    def log_query(self, query: str, response: str, feedback: dict = None) -> bool:
        """Logs a query and its response for monitoring."""
        pass

    @abstractmethod
    def collect_feedback(self, query: str, feedback: dict) -> bool:
        """Collects user feedback on the response."""
        pass

    @abstractmethod
    def monitor_performance(self) -> dict:
        """Monitors performance metrics like response time, accuracy, etc."""
        pass
