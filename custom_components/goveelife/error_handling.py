"""Error handling utilities for Govee Life integration."""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar, cast

_LOGGER = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def handle_api_errors(method: F) -> F:
    """Decorator to handle API errors consistently.

    Logs errors with context and returns None on failure.
    """

    @functools.wraps(method)
    async def async_wrapper(self, *args, **kwargs):
        method_name = method.__name__
        log_prefix = getattr(self, "log_prefix", "")

        try:
            return await method(self, *args, **kwargs)
        except ValueError:
            # Re-raise ValueError as it might be intentional validation
            raise
        except Exception:
            _LOGGER.error(
                f"{log_prefix}{self.name} {method_name} failed", exc_info=True
            )
            return None

    @functools.wraps(method)
    def sync_wrapper(self, *args, **kwargs):
        method_name = method.__name__
        log_prefix = getattr(self, "log_prefix", "")

        try:
            return method(self, *args, **kwargs)
        except ValueError:
            # Re-raise ValueError as it might be intentional validation
            raise
        except Exception:
            _LOGGER.error(
                f"{log_prefix}{self.name} {method_name} failed", exc_info=True
            )
            return None

    # Return appropriate wrapper based on whether method is async
    if asyncio.iscoroutinefunction(method):
        return cast(F, async_wrapper)
    else:
        return cast(F, sync_wrapper)


def log_errors(return_value: Any = None) -> Callable[[F], F]:
    """Decorator to log errors and return a specific value.

    Args:
        return_value: Value to return on error (default: None)
    """

    def decorator(method: F) -> F:
        @functools.wraps(method)
        async def async_wrapper(self, *args, **kwargs):
            method_name = method.__name__
            log_prefix = getattr(self, "log_prefix", "")

            try:
                return await method(self, *args, **kwargs)
            except Exception:
                _LOGGER.error(
                    f"{log_prefix}{self.name} {method_name} failed", exc_info=True
                )
                return return_value

        @functools.wraps(method)
        def sync_wrapper(self, *args, **kwargs):
            method_name = method.__name__
            log_prefix = getattr(self, "log_prefix", "")

            try:
                return method(self, *args, **kwargs)
            except Exception:
                _LOGGER.error(
                    f"{log_prefix}{self.name} {method_name} failed", exc_info=True
                )
                return return_value

        # Return appropriate wrapper based on whether method is async
        if asyncio.iscoroutinefunction(method):
            return cast(F, async_wrapper)
        else:
            return cast(F, sync_wrapper)

    return decorator
