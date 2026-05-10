from __future__ import annotations


class SelfHealError(Exception):
    """Base exception for SelfHeal domain errors."""


class CalendarError(SelfHealError):
    """Raised when a calendar provider operation fails."""


class LLMError(SelfHealError):
    """Raised when an LLM provider operation fails."""


class ClickUpError(SelfHealError):
    """Raised when a ClickUp provider operation fails."""


class ConfigError(SelfHealError):
    """Raised when configuration is invalid or incomplete."""


class SchedulerError(SelfHealError):
    """Raised when scheduling fails."""


class DaemonError(SelfHealError):
    """Raised when daemon operations fail."""
