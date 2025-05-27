"""Fan entities for the Govee Life integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .entities import GoveeLifePlatformEntity
from .error_handling import handle_api_errors
from .mixins import GoveeApiMixin
from .models import CapabilityType
from .platform_setup import setup_platform
from .work_mode_mixin import StateMappingMixin, WorkModeMixin

_LOGGER: Final = logging.getLogger(__name__)
platform = "fan"
platform_device_types = ["devices.types.air_purifier", "devices.types.fan"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the fan platform."""
    setup_platform(
        hass, entry, async_add_entities, platform, platform_device_types, GoveeLifeFan
    )


class GoveeLifeFan(
    FanEntity, GoveeLifePlatformEntity, GoveeApiMixin, StateMappingMixin, WorkModeMixin
):
    """Fan class for Govee Life integration."""

    @property
    def log_prefix(self) -> str:
        """Return a prefix for log messages."""
        return f"{self._api_id} - {self._identifier}: "

    def _init_platform_specific(self, **kwargs):
        """Platform specific initialization actions."""
        _LOGGER.debug(f"{self.log_prefix}_init_platform_specific")

        # Initialize mixin attributes
        self.init_state_mappings()
        self.init_work_mode_mappings()

        # Process capabilities
        for cap in self._device_cfg.get("capabilities", []):
            cap_type = cap.get("type", "")

            if cap_type == CapabilityType.ON_OFF.value:
                self._attr_supported_features |= FanEntityFeature.TURN_ON
                self.process_on_off_capability(cap)
            elif cap_type == CapabilityType.WORK_MODE.value:
                self._attr_supported_features |= FanEntityFeature.PRESET_MODE
                self.process_work_mode_capability(cap)
            else:
                _LOGGER.debug(
                    f"{self.log_prefix}_init_platform_specific: unhandled {cap=}"
                )

    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        return self._is_on()

    async def async_set_power(self, turn_on: bool, **kwargs) -> None:
        prefix = f"{self.log_prefix}async_set_power({turn_on=}): "
        _LOGGER.debug(f"{prefix}{kwargs=}")
        if self.is_on == turn_on:
            _LOGGER.debug(f"{prefix}already {self.is_on=}")
            return

        if await self._set_power_state(turn_on):
            self.async_write_ha_state()

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs
    ) -> None:
        """Turn the fan on."""
        await self.async_set_power(True, **kwargs)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the fan off."""
        await self.async_set_power(False, **kwargs)

    @property
    def preset_modes(self) -> list[str] | None:
        """Return the list of available preset modes."""
        return self._attr_available_modes or None

    @property
    def preset_mode(self) -> str | None:
        """Return the preset_mode of the entity."""
        prefix = f"{self.log_prefix}preset_mode: "

        match self._device_api.get_work_mode():
            case {"workMode": _, "modeValue": _} as search_value:
                # Find the preset mode name that matches this workMode/modeValue combination
                for (
                    mode_name,
                    mode_settings,
                ) in self._attr_preset_modes_mapping_set.items():
                    if mode_settings == search_value:
                        return mode_name
                _LOGGER.warning(
                    f"{prefix}Unknown work mode combination: {search_value}, "
                    f"valid modes: {self._attr_preset_modes_mapping_set}"
                )
                return None
            case _:
                _LOGGER.debug(f"{prefix}Invalid or missing work mode data")
                return None

    @handle_api_errors
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        prefix = f"{self.log_prefix}async_set_preset_mode: "
        if preset_mode not in self._attr_preset_modes_mapping_set:
            _LOGGER.error(
                f"{prefix}Invalid mode '{preset_mode}'. Valid modes: "
                f"{list(self._attr_preset_modes_mapping_set.keys())}"
            )
            raise ValueError(f"Invalid mode: {preset_mode}")

        mode_settings = self._attr_preset_modes_mapping_set[preset_mode]

        if await self._set_work_mode_from_mapping(mode_settings):
            self.async_write_ha_state()
