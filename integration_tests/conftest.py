# integration_tests/conftest.py
"""Pytest configuration for integration tests"""

import pytest
import os
import sys

# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Any shared fixtures or configuration can go here