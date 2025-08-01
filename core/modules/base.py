# maestrocat/modules/base.py
"""Base module class for MaestroCat"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..processors.event_emitter import EventEmitter

logger = logging.getLogger(__name__)


class MaestroCatModule(ABC):
    """Base class for MaestroCat modules"""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.enabled = True
        self.event_emitter: "Optional[EventEmitter]" = None

    def set_event_emitter(self, event_emitter: "EventEmitter"):
        """Set the event emitter for the module"""
        self.event_emitter = event_emitter

    @abstractmethod
    async def on_event(self, event_type: str, data: Any):
        """Handle events from the pipeline"""
        pass

    async def initialize(self):
        """Initialize the module"""
        pass

    async def cleanup(self):
        """Cleanup when module is unloaded"""
        pass
