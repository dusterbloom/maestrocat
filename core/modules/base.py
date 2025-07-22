# maestrocat/modules/base.py
"""Base module class for MaestroCat"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

from processors.module_loader import MaestroCatModule

logger = logging.getLogger(__name__)

