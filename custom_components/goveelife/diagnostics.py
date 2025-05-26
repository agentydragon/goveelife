"""Diagnostics support for the Govee Life integration."""

from __future__ import annotations
from importlib_metadata import version
from typing import (
    Final,
    Any,
)
import logging
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import (
    CONF_API_KEY,
    CONF_DEVICES,
    CONF_RESOURCE,
    CONF_STATE,
)

from .const import (
    DOMAIN,
)

REDACT_CONFIG = {CONF_API_KEY}
REDACT_CLOUD_DEVICES = {'dummy1', 'dummy2' }
REDACT_CLOUD_STATES = {'dummy1', 'dummy2' }

_LOGGER: Final = logging.getLogger(__name__)
platform='diagnostics'

async def async_get_config_entry_diagnostics( hass: HomeAssistant, entry: ConfigEntry ) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    prefix = f"{entry.entry_id} - async_get_config_entry_diagnostics {platform}: "
    _LOGGER.debug("Returning %s platform entry: %s", platform, entry.entry_id) 
    try:
        _LOGGER.debug(f"{prefix}Add config entry configuration to output")
        diag: dict[str, Any] = { "config": async_redact_data(entry.as_dict(), REDACT_CONFIG) }
    except Exception:
        _LOGGER.error(f"{prefix}Adding config entry configuration to output failed")
        #return False

    entry_data = hass.data[DOMAIN][entry.entry_id]
    try:
        _LOGGER.debug(f"{prefix}Add cloud received device list")
        diag["cloud_devices"] = async_redact_data(entry_data[CONF_DEVICES], REDACT_CLOUD_DEVICES)
    except Exception:
        _LOGGER.error(f"{prefix}Add cloud received device list failed")
        #return False
        
    try:
        _LOGGER.debug(f"{prefix}Add cloud received device states")
        diag["cloud_states"] = async_redact_data(entry_data[CONF_STATE], REDACT_CLOUD_STATES)
    except Exception:
        _LOGGER.error(f"{prefix}Add cloud received device states failed")
        #return False

    try:
        _LOGGER.debug(f"{prefix}Add python module [goveelife] version")
        diag["py_module_requests"] = version('requests')
    except Exception:
        _LOGGER.error(f"{prefix}Add python module [goveelife] version failed")
        #return False

    return diag
