"""Common platform setup utilities for Govee Life integration."""

from __future__ import annotations

import logging
from typing import Any, Callable, Final, Type

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICES, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_COORDINATORS, DOMAIN

_LOGGER: Final = logging.getLogger(__name__)


def setup_platform(
    hass: HomeAssistant,
    entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
    platform_name: str,
    platform_device_types: list[str],
    entity_class: Type[Entity],
    entity_factory: (
        Callable[[HomeAssistant, ConfigEntry, Any, dict, str], Entity] | None
    ) = None,
) -> None:
    """Set up a platform with common logic."""
    if not entity_factory:
        entity_factory = entity_class
    prefix = f"{entry.entry_id} - setup_platform {platform_name}: "
    _LOGGER.debug(
        "Setting up %s platform entry: %s | %s", platform_name, DOMAIN, entry.entry_id
    )
    try:
        _LOGGER.debug(f"{prefix}Getting cloud devices from data store")
        entry_data = hass.data[DOMAIN][entry.entry_id]
        api_devices = entry_data[CONF_DEVICES]
    except Exception:
        _LOGGER.error(f"{prefix}Getting cloud devices from data store failed")
        return

    entities = []
    for device_cfg in api_devices:
        if device_cfg.get("type", STATE_UNKNOWN) not in platform_device_types:
            continue
        device_id = device_cfg.get("device")
        _LOGGER.debug(f"{prefix}Setup device: {device_id}")
        try:
            coordinator = entry_data[CONF_COORDINATORS][device_id]
            entities.append(
                entity_factory(
                    hass, entry, coordinator, device_cfg, platform=platform_name
                )
            )
        except Exception:
            _LOGGER.error(f"{prefix}Setup device failed", exc_info=True)
            continue

    _LOGGER.info(f"{prefix}setup {len(entities)} {platform_name} entities")
    if entities:
        add_entities(entities)
