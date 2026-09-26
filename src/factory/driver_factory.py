import logging
from abc import ABC, abstractmethod
from typing import Any


class DriverFactory(ABC):
    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def create_driver(self, package: str, class_name: str) -> Any:
        """Create the database driver class."""
        pass
