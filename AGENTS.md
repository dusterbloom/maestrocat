
# MaestroCat Agent Guidelines

This document provides instructions for AI agents working on the MaestroCat codebase.

## Development Commands

- **Install all dependencies:** `pip install -e ".[dev]"`
- **Run linters:** `ruff check maestrocat/ core/`
- **Format code:** `black maestrocat/ core/`
- **Run all tests:** `python integration_tests/run_tests.py all`
- **Run specific tests:** `python integration_tests/run_tests.py [latency|stress]`
- **Run unit tests:** `pytest`
- **Run a specific unit test:** `pytest path/to/test_file.py::test_name`

## Code Style

- **Formatting:** Use `black` for automated code formatting.
- **Imports:** Follow standard Python conventions (e.g., `isort` compatibility).
- **Typing:** Use type hints for all function signatures and variables.
- **Naming:** Use `snake_case` for functions and variables, `PascalCase` for classes.
- **Error Handling:** Use `try...except` blocks for error handling.
- **Docstrings:** Use Google-style docstrings.
