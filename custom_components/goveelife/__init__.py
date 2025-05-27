"""Init for the Govee Life integration."""

from __future__ import annotations
from typing import Final
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_DEVICES,
    CONF_PARAMS,
    CONF_SCAN_INTERVAL,
)

from .const import (
    DOMAIN,
    CONF_COORDINATORS,
    FUNC_OPTION_UPDATES,
    SUPPORTED_PLATFORMS,
)
from .entities import (
    GoveeAPIUpdateCoordinator,
)
from .services import (
    async_registerService,
    async_service_SetPollInterval,
)
from .api import GoveeApiClient

_LOGGER: Final = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cloud resource from the config entry."""
    prefix = f"{entry.entry_id} - async_setup_entry: "
    _LOGGER.debug("Setting up config entry: %s", entry.entry_id)

    try:
        _LOGGER.debug(f"{prefix}Creating data store: {DOMAIN}.{entry.entry_id}")
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN].setdefault(entry.entry_id, {})
        entry_data = hass.data[DOMAIN][entry.entry_id]
        entry_data[CONF_PARAMS] = entry.data
        entry_data[CONF_SCAN_INTERVAL] = None
    except Exception:
        _LOGGER.error(f"{prefix}Creating data store failed")
        return False

    try:
        _LOGGER.debug(f"{prefix}Receiving cloud devices..")
        api_client = GoveeApiClient(hass, entry.entry_id)
        api_devices = await api_client.get_devices()
        if api_devices is None:
            return False
        entry_data[CONF_DEVICES] = api_devices
    except Exception:
        _LOGGER.error(f"{prefix}Receiving cloud devices failed")
        return False

    try:
        _LOGGER.debug(f"{prefix}Creating update coordinators per device..")
        entry_data.setdefault(CONF_COORDINATORS, {})
        for device_cfg in api_devices:
            # Get initial device state
            await api_client.get_device_state(device_cfg)
            coordinator = GoveeAPIUpdateCoordinator(hass, entry.entry_id, device_cfg)
            d = device_cfg.get("device")
            entry_data[CONF_COORDINATORS][d] = coordinator
    except Exception:
        _LOGGER.error(f"{prefix}Creating update coordinators failed")
        return False

    try:
        _LOGGER.debug(
            f"{prefix}Register option updates listener: {FUNC_OPTION_UPDATES}"
        )
        entry_data[FUNC_OPTION_UPDATES] = entry.add_update_listener(
            options_update_listener
        )
    except Exception:
        _LOGGER.error(f"{prefix}Register option updates listener failed")
        return False

    try:
        await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)
    except Exception:
        _LOGGER.error(f"{prefix}Setup trigger for platform failed")
        return False

    try:
        _LOGGER.debug(f"{prefix}register services")
        await async_registerService(
            hass, "set_poll_interval", async_service_SetPollInterval
        )
    except Exception:
        _LOGGER.error(f"{prefix}register services failed")
        return False

    _LOGGER.debug(f"{prefix}Completed")
    return True


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle options update."""
    _LOGGER.debug("Update options / reload config entry: %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    prefix = f"{entry.entry_id} - async_unload_entry: "
    try:
        _LOGGER.debug("Unloading config entry: %s", entry.entry_id)
        all_ok = True

        # Unload platforms
        for platform in SUPPORTED_PLATFORMS:
            _LOGGER.debug(f"{prefix}unload platform: {platform}")
            platform_ok = await hass.config_entries.async_forward_entry_unload(
                entry, platform
            )
            if not platform_ok:
                _LOGGER.error(f"{prefix}failed to unload: {platform} ({platform_ok})")
                all_ok = platform_ok

        if all_ok:
            # Remove entities from the entity registry
            entity_registry = hass.helpers.entity_registry.async_get()
            entities = hass.helpers.entity_registry.async_entries_for_config_entry(
                entity_registry, entry.entry_id
            )
            for entity in entities:
                _LOGGER.debug(f"{prefix}removing entity: {entity.entity_id}")
                entity_registry.async_remove(entity.entity_id)

            # Unload option updates listener
            _LOGGER.debug(
                f"{prefix}Unload option updates listener: {FUNC_OPTION_UPDATES}"
            )
            hass.data[DOMAIN][entry.entry_id][FUNC_OPTION_UPDATES]()

            # Remove data store
            _LOGGER.debug(f"{prefix}Remove data store: {DOMAIN}.{entry.entry_id}")
            hass.data[DOMAIN].pop(entry.entry_id)

        return all_ok
    except Exception:
        _LOGGER.error(f"{prefix}Unload device failed")
        return False
