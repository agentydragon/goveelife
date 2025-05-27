"""Climate entities for the Govee Life integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import GOVEE_TEMP_UNIT_CELSIUS
from .entities import GoveeLifePlatformEntity
from .error_handling import handle_api_errors
from .mixins import GoveeApiMixin
from .models import CapabilityType, temperature_setting
from .platform_setup import setup_platform
from .validators import validate_numeric_value
from .work_mode_mixin import StateMappingMixin, WorkModeMixin

_LOGGER: Final = logging.getLogger(__name__)
platform = "climate"
platform_device_types = [
    "devices.types.heater",
    "devices.types.kettle",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the climate platform."""
    setup_platform(
        hass,
        entry,
        async_add_entities,
        platform,
        platform_device_types,
        GoveeLifeClimate,
    )


class GoveeLifeClimate(
    ClimateEntity,
    GoveeLifePlatformEntity,
    GoveeApiMixin,
    StateMappingMixin,
    WorkModeMixin,
):
    """Climate class for Govee Life integration."""

    _attr_hvac_modes = []
    _attr_hvac_modes_mapping = {}
    _attr_hvac_modes_mapping_set = {}
    _enable_turn_on_off_backwards_compatibility = False

    @property
    def log_prefix(self) -> str:
        """Return a prefix for log messages."""
        return f"{self._api_id} - {self._identifier}: "

    def _init_platform_specific(self, **kwargs):
        """Platform specific init actions."""
        _LOGGER.debug(f"{self.log_prefix}_init_platform_specific")

        # Initialize mixin attributes
        self.init_work_mode_mappings()

        # Process capabilities
        for cap in self._device_cfg.get("capabilities", []):
            if cap["type"] == CapabilityType.ON_OFF.value:
                for option in cap["parameters"]["options"]:
                    if option["name"] == "on":
                        self._attr_supported_features |= ClimateEntityFeature.TURN_ON
                        self._attr_hvac_modes.append(HVACMode.HEAT_COOL)
                        self._attr_hvac_modes_mapping[option["value"]] = (
                            HVACMode.HEAT_COOL
                        )
                        self._attr_hvac_modes_mapping_set[HVACMode.HEAT_COOL] = option[
                            "value"
                        ]
                    elif option["name"] == "off":
                        self._attr_supported_features |= ClimateEntityFeature.TURN_OFF
                        self._attr_hvac_modes.append(HVACMode.OFF)
                        self._attr_hvac_modes_mapping[option["value"]] = HVACMode.OFF
                        self._attr_hvac_modes_mapping_set[HVACMode.OFF] = option[
                            "value"
                        ]
                    else:
                        _LOGGER.warning(
                            f"{self.log_prefix}_init_platform_specific: unknown on_off option: {option}"
                        )
            elif cap["type"] == CapabilityType.TEMPERATURE_SETTING.value and (
                cap["instance"] in ["targetTemperature", "sliderTemperature"]
            ):
                self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
                for field in cap["parameters"]["fields"]:
                    if field["fieldName"] == "temperature":
                        self._attr_max_temp = field["range"]["max"]
                        self._attr_min_temp = field["range"]["min"]
                        self._attr_target_temperature_step = field["range"]["precision"]
                    elif field["fieldName"] == "unit":
                        self._attr_temperature_unit = UnitOfTemperature[
                            field["defaultValue"].upper()
                        ]
                    elif field["fieldName"] == "autoStop":
                        pass  # TO-BE-DONE: implement as switch entity type
            elif cap["type"] == CapabilityType.WORK_MODE.value:
                self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
                # Use mixin to process work modes
                self.process_work_mode_capability(cap)
                # Climate specific: ensure preset_modes list exists
                if not hasattr(self, "_attr_preset_modes"):
                    self._attr_preset_modes = list(
                        self._attr_preset_modes_mapping.keys()
                    )
            elif (
                cap["type"] == CapabilityType.PROPERTY.value
                and cap["instance"] == "sensorTemperature"
            ):
                pass  # do nothing as this is handled within 'current_temperature' property
            else:
                _LOGGER.debug(
                    f"{self.log_prefix}_init_platform_specific: cap unhandled: {cap=}"
                )

    @property
    def hvac_mode(self) -> str:
        """Return the hvac_mode of the entity."""
        prefix = f"{self.log_prefix}hvac_mode: "
        value = self._device_api.get_on_off_value()
        if value is None:
            _LOGGER.warning(f"{prefix}No power state cached")
            return HVACMode.OFF

        hvac_mode = self._attr_hvac_modes_mapping.get(value, STATE_UNKNOWN)
        if hvac_mode == STATE_UNKNOWN:
            _LOGGER.warning(f"{prefix}invalid {value=}")
            _LOGGER.debug(f"{prefix}valid are: {self._attr_hvac_modes_mapping=}")
        return hvac_mode

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self._attr_hvac_modes_mapping_set:
            _LOGGER.error(f"{self.log_prefix}Invalid HVAC mode: {hvac_mode}")
            return

        power_value = self._attr_hvac_modes_mapping_set[hvac_mode]
        if hvac_mode == HVACMode.OFF:
            success = await self._device_api.turn_off(power_value)
        else:
            success = await self._device_api.turn_on(power_value)

        if success:
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEATING)

    @property
    def preset_mode(self) -> str | None:
        """Return the preset_mode of the entity."""
        value = self._device_api.get_work_mode()
        if not value:
            return None

        work_mode = value.get("workMode")
        if work_mode is None:
            return None

        # Find the preset mode name that matches this workMode value
        for preset_name, preset_value in self._attr_preset_modes_mapping.items():
            if preset_value == work_mode:
                return preset_name

        return None

    @handle_api_errors
    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set new target preset mode."""
        if preset_mode not in self._attr_preset_modes_mapping_set:
            _LOGGER.error(
                f"{self.log_prefix}Invalid preset mode '{preset_mode}'. Valid modes: "
                f"{list(self._attr_preset_modes_mapping_set.keys())}"
            )
            raise ValueError(f"Invalid preset mode: {preset_mode}")

        mode_settings = self._attr_preset_modes_mapping_set[preset_mode]

        if await self._set_work_mode_from_mapping(mode_settings):
            self.async_write_ha_state()

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit of the entity."""
        # Check both possible instances
        for instance in ["targetTemperature", "sliderTemperature"]:
            value = self._get_cached_value(CapabilityType.TEMPERATURE_SETTING, instance)
            if value is None:
                continue
            return UnitOfTemperature[value.get("unit", "CELSIUS").upper()]

        return UnitOfTemperature.CELSIUS  # Default

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature of the entity."""
        # First try to get the temperature from the current preset mode
        preset_mode = self.preset_mode
        if preset_mode and preset_mode in self._attr_preset_modes_mapping_set:
            mode_value = self._attr_preset_modes_mapping_set[preset_mode].get(
                "modeValue"
            )
            if mode_value is not None and mode_value != 0:
                return validate_numeric_value(
                    mode_value, "preset temperature", self.log_prefix
                )

        # If no preset mode temperature, try to get it from the slider
        value = self._get_cached_value(
            CapabilityType.TEMPERATURE_SETTING, "sliderTemperature"
        )
        if value is None:
            return None
        temperature = value.get("targetTemperature")
        if temperature is None:
            return None
        return validate_numeric_value(
            temperature, "target temperature", self.log_prefix
        )

    async def async_set_temperature(self, temperature: float) -> None:
        """Set new target temperature."""
        # Check both possible instances
        for instance in ["targetTemperature", "sliderTemperature"]:
            value = self._get_cached_value(CapabilityType.TEMPERATURE_SETTING, instance)
            if value is None:
                continue
            # Send to API with the unit format Govee expects (title case)
            capability = temperature_setting(
                instance=instance,
                temperature=temperature,
                unit=value.get("unit", GOVEE_TEMP_UNIT_CELSIUS),
            )
            if await self._device_api.control_device(capability):
                self.async_write_ha_state()
                return

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature of the entity."""
        value = self._get_cached_value(CapabilityType.PROPERTY, "sensorTemperature")
        if value is None or value == "":
            return None
        numeric_value = validate_numeric_value(value, "temperature", self.log_prefix)
        if numeric_value is None:
            return None
        if self.temperature_unit == UnitOfTemperature.CELSIUS:
            # Value seems to be always Fahrenheit - calculate to °C if necessary
            numeric_value = (numeric_value - 32) * 5 / 9
        return numeric_value
