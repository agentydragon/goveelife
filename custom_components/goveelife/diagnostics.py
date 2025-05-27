"""Diagnostics support for the Govee Life integration."""

from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_DEVICES, CONF_STATE
from homeassistant.core import HomeAssistant
from importlib_metadata import version

from .const import DOMAIN
from .error_handling import log_errors

REDACT_CONFIG = {CONF_API_KEY}
REDACT_CLOUD_DEVICES = {"dummy1", "dummy2"}
REDACT_CLOUD_STATES = {"dummy1", "dummy2"}

_LOGGER: Final = logging.getLogger(__name__)
platform = "diagnostics"


@log_errors
async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    prefix = f"{entry.entry_id} - async_get_config_entry_diagnostics {platform}: "
    _LOGGER.debug("Returning %s platform entry: %s", platform, entry.entry_id)

    diag: dict[str, Any] = {}

    # Add config entry configuration
    _LOGGER.debug(f"{prefix}Add config entry configuration to output")
    diag["config"] = async_redact_data(entry.as_dict(), REDACT_CONFIG)

    entry_data = hass.data[DOMAIN][entry.entry_id]

    # Add cloud received device list
    _LOGGER.debug(f"{prefix}Add cloud received device list")
    diag["cloud_devices"] = async_redact_data(
        entry_data[CONF_DEVICES], REDACT_CLOUD_DEVICES
    )

    # Add cloud received device states
    _LOGGER.debug(f"{prefix}Add cloud received device states")
    diag["cloud_states"] = async_redact_data(
        entry_data[CONF_STATE], REDACT_CLOUD_STATES
    )

    # Add python module version
    _LOGGER.debug(f"{prefix}Add python module [goveelife] version")
    diag["py_module_requests"] = version("requests")

    return diag
