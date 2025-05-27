"""Switch entities for the Govee Life integration."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Final

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICES, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .const import CONF_COORDINATORS, DOMAIN
from .entities import GoveeLifePlatformEntity
from .error_handling import handle_api_errors, log_errors
from .mixins import GoveeApiMixin
from .models import Capability, CapabilityType
from .work_mode_mixin import StateMappingMixin

_LOGGER: Final = logging.getLogger(__name__)
platform = "switch"

platform_device_types = [
    "devices.types.heater:.*on_off:.*",
    "devices.types.heater:.*toggle:oscillationToggle",
    "devices.types.fan:.*toggle:oscillationToggle",
    "devices.types.socket:.*on_off:.*",
    "devices.types.socket:.*toggle:.*",
    "devices.types.light:.*toggle:gradientToggle",
    "devices.types.ice_maker:.*on_off:.*",
    "devices.types.aroma_diffuser:.*on_off:.*",
    "devices.types.humidifier:.*on_off:.*",
    "devices.types.humidifier:.*toggle:nightlightToggle",
    "devices.types.kettle:.*on_off:.*",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the switch platform."""

    # Switch platform needs custom entity factory for capability-based entities
    @log_errors
    async def switch_entity_factory(hass, entry, coordinator, device_cfg, platform):
        entities = []
        for capability in device_cfg.get("capabilities", []):
            capability_key = f"{device_cfg.get('type', STATE_UNKNOWN)}:{capability.get('type', STATE_UNKNOWN)}:{capability.get('instance', STATE_UNKNOWN)}"
            if any(
                re.match(platform_match, capability_key)
                for platform_match in platform_device_types
            ):
                entity = GoveeLifeSwitch(
                    hass,
                    entry,
                    coordinator,
                    device_cfg,
                    platform=platform,
                    cap=capability,
                )
                entities.append(entity)
        return entities

    # Use modified setup that returns entities list
    prefix = f"{entry.entry_id} - async_setup_entry {platform}: "
    _LOGGER.debug(
        "Setting up %s platform entry: %s | %s", platform, DOMAIN, entry.entry_id
    )
    entities = []

    entry_data = hass.data[DOMAIN][entry.entry_id]
    api_devices = entry_data[CONF_DEVICES]

    for device_cfg in api_devices:
        device = device_cfg.get("device")
        coordinator = entry_data[CONF_COORDINATORS][device]
        device_entities = await switch_entity_factory(
            hass, entry, coordinator, device_cfg, platform
        )
        entities.extend(device_entities)
        await asyncio.sleep(0)

    _LOGGER.info(f"{prefix}setup {len(entities)} {platform} entities")
    if entities:
        async_add_entities(entities)


class GoveeLifeSwitch(
    SwitchEntity, GoveeLifePlatformEntity, GoveeApiMixin, StateMappingMixin
):
    """Switch class for Govee Life integration.\" """

    def _init_platform_specific(self, cap=None, **kwargs):
        """Platform specific initialization."""
        self._cap = cap
        self._name = f"{self._name} {str(self._cap['instance']).capitalize()}"
        self._entity_id = f"{self._entity_id}_{self._cap['instance']}"
        self.uniqueid = f"{self._identifier}_{self._entity_id}"

        # Initialize mixin attributes
        self.init_state_mappings()

        # Process capability
        self.process_on_off_capability(self._cap)

    @property
    def state(self) -> str | None:
        """Return the current state of the switch."""
        # Get capability type enum from string
        cap_type_str = self._cap.get("type", STATE_UNKNOWN)
        try:
            cap_type = CapabilityType(cap_type_str)
        except ValueError:
            return STATE_UNKNOWN

        if (
            value := self._get_cached_value(
                cap_type, self._cap.get("instance", STATE_UNKNOWN)
            )
        ) is None:
            return STATE_UNKNOWN
        return self._state_mapping.get(value, STATE_UNKNOWN)

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self.state == STATE_ON

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._set_switch_state(STATE_ON)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._set_switch_state(STATE_OFF)

    @handle_api_errors
    async def _set_switch_state(self, state: str) -> None:
        """Set switch state."""
        prefix = f"{self._api_id} - {self._identifier}: _set_switch_state {state}"
        _LOGGER.debug(prefix)

        if state not in self._state_mapping_set:
            _LOGGER.error(f"{prefix}: State {state} not in mapping")
            return

        capability = Capability(
            type=self._cap["type"],
            instance=self._cap["instance"],
            value=self._state_mapping_set[state],
        )
        if await self._device_api.control_device(capability):
            self.async_write_ha_state()
