"""Support for dScriptModule services."""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Final

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, ServiceCall

from .const import CONF_ENTRY_ID, DOMAIN
from .error_handling import log_errors

_LOGGER: Final = logging.getLogger(__name__)


@log_errors
async def async_registerService(hass: HomeAssistant, name: str, service) -> None:
    """Register a service if it does not already exist"""
    _LOGGER.debug("%s - async_registerService: %s", DOMAIN, name)
    await asyncio.sleep(0)
    if not hass.services.has_service(DOMAIN, name):
        hass.services.async_register(DOMAIN, name, functools.partial(service, hass))
    else:
        _LOGGER.debug(
            "%s - async_registerServic: service already exists: %s", DOMAIN, name
        )


@log_errors
async def async_service_SetPollInterval(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to set the poll interval to reduece requests"""
    scan_interval = call.data.get(CONF_SCAN_INTERVAL)
    if scan_interval is None:
        _LOGGER.error(
            "%s - async_service_SetPollInterval: %s is a required parameter",
            DOMAIN,
            CONF_SCAN_INTERVAL,
        )
        return

    entry_id = call.data.get(CONF_ENTRY_ID)
    if entry_id is None:
        _LOGGER.error(
            "%s - async_service_SetPollInterval: %s is a required parameter",
            DOMAIN,
            CONF_ENTRY_ID,
        )
        return

    hass.data[DOMAIN][entry_id][CONF_SCAN_INTERVAL] = scan_interval
    _LOGGER.info(
        "%s - async_service_SetPollInterval: Poll interval updated to %s seconds - change active after next poll",
        DOMAIN,
        scan_interval,
    )
