from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("selfheal")
except PackageNotFoundError:
    __version__ = "0.1.0"

from .errors import (
    CalendarError,
    ClickUpError,
    ConfigError,
    DaemonError,
    LLMError,
    SchedulerError,
    SelfHealError,
)
from .result import Result
from .retry import retry_async, retry_sync

__all__ = [
    "__version__",
    "CalendarError",
    "ClickUpError",
    "ConfigError",
    "DaemonError",
    "LLMError",
    "Result",
    "SchedulerError",
    "SelfHealError",
    "retry_async",
    "retry_sync",
]
