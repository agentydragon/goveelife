"""Sensor entities for the Govee Life integration."""

from __future__ import annotations
from typing import Final
import logging
import math

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.const import (
    STATE_ON,
    STATE_UNKNOWN,
)

from .entities import GoveeLifePlatformEntity
from .error_handling import handle_api_errors
from .mixins import GoveeApiMixin
from .models import (
    CapabilityType,
    brightness_range,
    color_rgb,
    color_temperature,
)
from .platform_setup import setup_platform
from .work_mode_mixin import StateMappingMixin

_LOGGER: Final = logging.getLogger(__name__)
platform = "light"
platform_device_types = ["devices.types.light"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the light platform."""
    setup_platform(
        hass, entry, async_add_entities, platform, platform_device_types, GoveeLifeLight
    )


class GoveeLifeLight(
    LightEntity, GoveeLifePlatformEntity, GoveeApiMixin, StateMappingMixin
):
    """Light class for Govee Life integration."""

    _attr_supported_color_modes = set()

    def _init_platform_specific(self, **kwargs):
        """Platform specific init actions"""
        prefix = f"{self._api_id} - {self._identifier}: _init_platform_specific"
        _LOGGER.debug(prefix)

        # Initialize mixin attributes
        self.init_state_mappings()

        # Process capabilities
        for cap in self._device_cfg.get("capabilities", []):
            if cap["type"] == "devices.capabilities.on_off":
                self._attr_supported_color_modes.add(ColorMode.ONOFF)
                self.process_on_off_capability(cap)
            elif (
                cap["type"] == "devices.capabilities.range"
                and cap["instance"] == "brightness"
            ):
                self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
                self._brightness_scale = (
                    cap["parameters"]["range"]["min"],
                    cap["parameters"]["range"]["max"],
                )
            elif (
                cap["type"] == "devices.capabilities.color_setting"
                and cap["instance"] == "colorRgb"
            ):
                self._attr_supported_color_modes.add(ColorMode.RGB)
            elif (
                cap["type"] == "devices.capabilities.color_setting"
                and cap["instance"] == "colorTemperatureK"
            ):
                self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
                self._attr_min_color_temp_kelvin = cap["parameters"]["range"]["min"]
                self._attr_max_color_temp_kelvin = cap["parameters"]["range"]["max"]
            elif (
                cap["type"] == "devices.capabilities.toggle"
                and cap["instance"] == "gradientToggle"
            ):
                pass  # implemented as switch entity type
            elif cap["type"] == "devices.capabilities.segment_color_setting":
                pass  # TO-BE-DONE - implement as service?
            elif cap["type"] == "devices.capabilities.dynamic_scene":
                pass  # TO-BE-DONE: implement as select entity type
            elif cap["type"] == "devices.capabilities.music_setting":
                pass  # TO-BE-DONE: implement as select entity type
            elif cap["type"] == "devices.capabilities.dynamic_setting":
                pass  # TO-BE-DONE: implement as select ? unsure about setting effect
            else:
                _LOGGER.debug(f"{prefix}: cap unhandled: {cap=}")

    def _getRGBfromI(self, RGBint):
        blue = RGBint & 255
        green = (RGBint >> 8) & 255
        red = (RGBint >> 16) & 255
        return red, green, blue

    def _getIfromRGB(self, rgb):
        red = rgb[0]
        green = rgb[1]
        blue = rgb[2]
        RGBint = (red << 16) + (green << 8) + blue
        return RGBint

    @property
    def state(self) -> str | None:
        """Return the current state of the entity."""
        value = self._device_api.get_on_off_value()
        if value is None:
            return STATE_UNKNOWN
        v = self._state_mapping.get(value, STATE_UNKNOWN)
        if v == STATE_UNKNOWN:
            _LOGGER.warning(f"{self.log_prefix}state: invalid {value=}")
            _LOGGER.debug(f"{self.log_prefix}state: valid are: {self._state_mapping=}")
        return v

    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        return self.state == STATE_ON

    @property
    def brightness(self) -> int | None:
        """Return the current brightness."""
        value = self._get_cached_value(CapabilityType.RANGE, "brightness")
        if value is None:
            return None
        return value_to_brightness(self._brightness_scale, value)

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        value = self._get_cached_value(
            CapabilityType.COLOR_SETTING, "colorTemperatureK"
        )
        return value

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color."""
        value = self._get_cached_value(CapabilityType.COLOR_SETTING, "colorRgb")
        if value is None:
            return None
        return self._getRGBfromI(value)

    @handle_api_errors
    async def async_turn_on(self, **kwargs) -> None:
        """Async: Turn entity on"""
        prefix = f"{self._api_id} - {self._identifier}: async_turn_on"
        _LOGGER.debug(prefix)

        # Extract specific parameters
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        rgb_color = kwargs.get(ATTR_RGB_COLOR)

        _LOGGER.debug(f"{prefix}: {brightness=}, {color_temp_kelvin=}, {rgb_color=}")

        if brightness is not None:
            capability = brightness_range(
                value=math.ceil(brightness_to_value(self._brightness_scale, brightness))
            )
            if await self._device_api.control_device(capability):
                self.async_write_ha_state()

        if color_temp_kelvin is not None:
            capability = color_temperature(value=color_temp_kelvin)
            if await self._device_api.control_device(capability):
                self.async_write_ha_state()

        if rgb_color is not None:
            capability = color_rgb(value=self._getIfromRGB(rgb_color))
            if await self._device_api.control_device(capability):
                self.async_write_ha_state()

        # Turn on the device if not already on
        if self.is_on:
            _LOGGER.debug(f"{prefix}: device already on")
            return

        if await self._turn_on():
            self.async_write_ha_state()

    @handle_api_errors
    async def async_turn_off(self, **kwargs) -> None:
        """Async: Turn entity off"""
        prefix = f"{self._api_id} - {self._identifier}: async_turn_off"
        _LOGGER.debug(prefix)
        _LOGGER.debug(f"{prefix}: {kwargs=}")

        if not self.is_on:
            _LOGGER.debug(f"{prefix}: device already off")
            return

        if await self._turn_off():
            self.async_write_ha_state()
