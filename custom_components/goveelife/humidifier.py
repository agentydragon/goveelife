"""Humidifier entities for the Govee Life integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from .entities import GoveeLifePlatformEntity
from .error_handling import handle_api_errors
from .mixins import GoveeApiMixin
from .models import CapabilityType
from .platform_setup import setup_platform
from .validators import validate_numeric_value

_LOGGER: Final = logging.getLogger(__name__)
platform = "humidifier"
platform_device_types = ["devices.types.humidifier", "devices.types.dehumidifier"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the humidifier platform."""
    setup_platform(
        hass,
        entry,
        async_add_entities,
        platform,
        platform_device_types,
        GoveeLifeHumidifier,
    )


class GoveeLifeHumidifier(HumidifierEntity, GoveeLifePlatformEntity, GoveeApiMixin):
    """Humidifier class for Govee Life integration."""

    _state_mapping = {}
    _state_mapping_set = {}
    _attr_available_modes = []
    _attr_preset_modes_mapping = {}
    _attr_preset_modes_mapping_set = {}
    _last_mode = None
    _last_humidity_by_mode = {}

    @property
    def log_prefix(self) -> str:
        """Return a prefix for log messages."""
        return f"{self._api_id} - {self._identifier}: "

    def _init_platform_specific(self, **kwargs):
        """Platform specific initialization actions."""
        _LOGGER.debug(f"{self.log_prefix}_init_platform_specific")

        # Set device class
        self.device_class = self._device_cfg.get("type", [])
        if self.device_class == "devices.types.humidifier":
            self._attr_device_class = HumidifierDeviceClass.HUMIDIFIER
        elif self.device_class == "devices.types.dehumidifier":
            self._attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER

        # Process capabilities
        for cap in self._device_cfg.get("capabilities", []):
            self._process_capability(cap)

    def _process_capability(self, cap: dict) -> None:
        """Process a single capability."""
        cap_type = cap.get("type", "")

        if cap_type == CapabilityType.ON_OFF.value:
            self._process_on_off_capability(cap)
        elif cap_type == CapabilityType.WORK_MODE.value:
            self._process_work_mode_capability(cap)
        elif (
            cap_type == CapabilityType.RANGE.value and cap.get("instance") == "humidity"
        ):
            self._process_humidity_range_capability(cap)
        else:
            _LOGGER.debug(f"{self.log_prefix}_process_capability: unhandled {cap=}")

    def _process_on_off_capability(self, cap: dict) -> None:
        """Process on/off capability."""
        for option in cap["parameters"]["options"]:
            if option["name"] == "on":
                self._state_mapping[option["value"]] = STATE_ON
                self._state_mapping_set[STATE_ON] = option["value"]
            elif option["name"] == "off":
                self._state_mapping[option["value"]] = STATE_OFF
                self._state_mapping_set[STATE_OFF] = option["value"]
            else:
                _LOGGER.warning(
                    f"{self.log_prefix}_process_on_off_capability: unhandled option: {option}"
                )

    def _process_work_mode_capability(self, cap: dict) -> None:
        """Process work mode capability."""
        self._attr_supported_features |= HumidifierEntityFeature.MODES

        for field in cap["parameters"]["fields"]:
            if field["fieldName"] == "workMode":
                self._process_work_mode_field(field)
            elif field["fieldName"] == "modeValue":
                self._process_mode_value_field(field)

    def _process_work_mode_field(self, field: dict) -> None:
        """Process workMode field."""
        for work_option in field.get("options", []):
            self._attr_preset_modes_mapping[work_option["name"]] = work_option["value"]

    def _process_mode_value_field(self, field: dict) -> None:
        """Process modeValue field."""
        for mode_value_option in field.get("options", []):
            if "options" in mode_value_option:
                self._process_parent_mode_with_children(mode_value_option)
            elif mode_value_option["name"] != "Custom":
                self._process_standalone_mode(mode_value_option)

    def _process_parent_mode_with_children(self, mode_value_option: dict) -> None:
        """Process a parent mode that has child options (like gearMode)."""
        parent_mode_name = mode_value_option["name"]

        for child_option in mode_value_option["options"]:
            child_name = child_option["name"]
            self._attr_available_modes.append(child_name)
            # TODO: Replace dict with Pydantic model or dataclass for type safety
            self._attr_preset_modes_mapping_set[child_name] = {
                "workMode": self._attr_preset_modes_mapping[parent_mode_name],
                "modeValue": child_option["value"],
            }
            _LOGGER.debug(
                f"{self.log_prefix}Adding preset mode '{child_name}': "
                f"{self._attr_preset_modes_mapping_set[child_name]}"
            )

    def _process_standalone_mode(self, mode_value_option: dict) -> None:
        """Process a standalone mode without child options."""
        mode_name = mode_value_option["name"]
        self._attr_available_modes.append(mode_name)

        # Extract mode value from various possible structures
        mode_value = self._extract_mode_value(mode_value_option)

        # TODO: Replace dict with Pydantic model or dataclass for type safety
        # e.g., PresetModeSettings(work_mode=..., mode_value=...)
        self._attr_preset_modes_mapping_set[mode_name] = {
            "workMode": self._attr_preset_modes_mapping[mode_name],
            "modeValue": mode_value,
        }

    def _extract_mode_value(self, mode_value_option: dict) -> int:
        """Extract mode value from various option structures.

        TODO: Better solutions could include:
        1. For ranges, create multiple presets (e.g., "Auto 30%", "Auto 50%", "Auto 80%")
        2. Expose a separate humidity target control when in Auto mode
        3. Use the range to set min/max constraints on a slider control
        4. Query the device's current modeValue when in that mode and use it
        """
        if "value" in mode_value_option:
            return mode_value_option["value"]
        elif "defaultValue" in mode_value_option:
            return mode_value_option["defaultValue"]
        elif "range" in mode_value_option:
            # For Auto mode with range, use the min value
            return mode_value_option["range"].get("min", 0)
        else:
            _LOGGER.warning(
                f"{self.log_prefix}No value found for mode {mode_value_option['name']}, using 0"
            )
            return 0

    def _process_humidity_range_capability(self, cap: dict) -> None:
        """Process humidity range capability."""
        range_params = cap["parameters"]["range"]
        self._attr_min_humidity = range_params["min"]
        self._attr_max_humidity = range_params["max"]

    @property
    def current_humidity(self) -> float:
        """Return current humidity."""
        prefix = f"{self.log_prefix}current_humidity: "
        value = self._get_cached_value(CapabilityType.RANGE, "humidity")
        _LOGGER.debug(f"{prefix}raw value = {value!r}")

        # XXX (2025-05-26): The above seems to sometimes return ''
        return validate_numeric_value(value, "humidity", prefix)

    @property
    def target_humidity(self) -> int | None:
        """Return the target humidity."""
        prefix = f"{self.log_prefix}target_humidity: "
        # For now, return the current preset mode's modeValue if it represents humidity
        # This is a simplification - some devices may have a separate target humidity capability
        preset = self.preset_mode
        if not preset:
            _LOGGER.debug(f"{prefix}No preset mode set")
            return None

        if preset not in self._attr_preset_modes_mapping_set:
            _LOGGER.warning(f"{prefix}Preset mode '{preset}' not in mapping")
            return None

        mode_settings = self._attr_preset_modes_mapping_set[preset]
        mode_value = mode_settings.get("modeValue")

        if mode_value is None:
            _LOGGER.debug(f"{prefix}No modeValue in settings for preset '{preset}'")
            return None

        # Check if mode value is within humidity range
        if self._is_humidity_value(mode_value):
            _LOGGER.debug(f"{prefix}{mode_value} from preset {preset}")
            return mode_value

        _LOGGER.debug(
            f"{prefix}modeValue {mode_value} not a humidity value for preset {preset}"
        )
        return None

    def _is_humidity_value(self, value: int) -> bool:
        """Check if a value represents a humidity percentage."""
        if not hasattr(self, "_attr_min_humidity") or not hasattr(
            self, "_attr_max_humidity"
        ):
            return False
        return self._attr_min_humidity <= value <= self._attr_max_humidity

    def _has_humidity_control(self) -> bool:
        """Check if device supports humidity control."""
        return hasattr(self, "_attr_min_humidity") and hasattr(
            self, "_attr_max_humidity"
        )

    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        prefix = f"{self.log_prefix}is_on: "
        value = self._device_api.get_on_off_value()
        if value is None:
            _LOGGER.warning(f"{prefix}No power state cached")
            return False

        if (mapped_state := self._state_mapping.get(value)) is None:
            _LOGGER.warning(f"{prefix}Unknown power state value: {value}")
            return False

        return mapped_state == STATE_ON

    @property
    def mode(self) -> str | None:
        """Return current mode."""
        # Home Assistant uses 'mode' for basic modes like auto/manual
        # We use preset_mode for device-specific modes
        return None

    @property
    def available_modes(self) -> list[str] | None:
        """Return available modes."""
        return self._attr_available_modes

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
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

    async def async_turn_on(self, **kwargs) -> None:
        """Async: Turn entity on"""
        prefix = f"{self.log_prefix}async_turn_on: "
        _LOGGER.debug(f"{prefix}{kwargs=}")
        if self.is_on:
            _LOGGER.debug(f"{prefix}device already on")
            return

        if await self._turn_on():
            # Restore last mode if available
            if self._last_mode and self._last_mode in self._attr_preset_modes_mapping_set:
                _LOGGER.debug(f"{prefix}Restoring last mode: {self._last_mode}")
                try:
                    await self.async_set_mode(self._last_mode)
                except Exception as e:
                    _LOGGER.warning(
                        f"{prefix}Failed to restore mode {self._last_mode}"
                    )
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Async: Turn entity off"""
        prefix = f"{self.log_prefix}async_turn_off: "
        _LOGGER.debug(f"{prefix}{kwargs=}")
        if not self.is_on:
            _LOGGER.debug(f"{prefix}device already off")
            return

        if await self._turn_off():
            self.async_write_ha_state()

    @handle_api_errors
    async def async_set_mode(self, mode: str) -> None:
        """Set new target preset mode."""
        prefix = f"{self.log_prefix}async_set_mode: "
        if mode not in self._attr_preset_modes_mapping_set:
            _LOGGER.error(
                f"{prefix}Invalid mode '{mode}'. Valid modes: "
                f"{list(self._attr_preset_modes_mapping_set.keys())}"
            )
            raise ValueError(f"Invalid mode: {mode}")

        mode_settings = self._attr_preset_modes_mapping_set[mode]
        
        # Validate mode settings before attempting to set
        work_mode = mode_settings.get("workMode")
        mode_value = mode_settings.get("modeValue")
        
        if work_mode not in self._attr_preset_modes_mapping.values():
            _LOGGER.error(
                f"{prefix}Work mode {work_mode} not supported by device"
            )
            raise ValueError(f"Work mode {work_mode} not supported")
        
        # If mode has a humidity value, validate it's within range
        if mode_value is not None and self._is_humidity_value(mode_value):
            if not self._has_humidity_control():
                _LOGGER.error(
                    f"{prefix}Device does not support humidity control for mode {mode}"
                )
                raise ValueError("Device does not support humidity control")

        if await self._set_work_mode_from_mapping(mode_settings):
            # Store last mode for persistence
            self._last_mode = mode
            
            # Restore last humidity for this mode if it's a humidity-controllable mode
            if mode_value is not None and self._is_humidity_value(mode_value):
                last_humidity = self._last_humidity_by_mode.get(mode)
                if last_humidity is not None:
                    _LOGGER.debug(
                        f"{prefix}Restoring humidity {last_humidity} for mode {mode}"
                    )
                    # Set the humidity value if different from mode's default
                    if last_humidity != mode_value:
                        await self._set_range_value("humidity", last_humidity)
                        
            self.async_write_ha_state()

    @handle_api_errors
    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity level."""
        prefix = f"{self.log_prefix}async_set_humidity: "

        if not self._has_humidity_control():
            _LOGGER.error(f"{prefix}Device does not support humidity control")
            return

        if not self._is_humidity_value(humidity):
            _LOGGER.error(
                f"{prefix}Humidity {humidity} out of range "
                f"({self._attr_min_humidity}-{self._attr_max_humidity})"
            )
            raise ValueError(
                f"Humidity must be between {self._attr_min_humidity} and {self._attr_max_humidity}"
            )

        if await self._set_range_value("humidity", humidity):
            # Store humidity setting for current mode
            current_mode = self.preset_mode
            if current_mode:
                self._last_humidity_by_mode[current_mode] = humidity
                _LOGGER.debug(
                    f"{prefix}Saved humidity {humidity} for mode {current_mode}"
                )
            self.async_write_ha_state()
