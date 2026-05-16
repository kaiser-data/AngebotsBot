"""Scraper package.

Avoid importing Playwright-backed implementations at package import time so
utility modules remain testable without browser dependencies installed.
"""

__all__ = ["kaufda", "models", "utils"]
