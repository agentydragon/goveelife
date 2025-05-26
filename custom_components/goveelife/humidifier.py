"""Humidifier entities for the Govee Life integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from homeassistant.components.humidifier import (MODE_AUTO,
                                                 HumidifierDeviceClass,
                                                 HumidifierEntity,
                                                 HumidifierEntityFeature)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_DEVICES, STATE_OFF, STATE_ON,
                                 STATE_UNKNOWN)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_COORDINATORS, DOMAIN
from .entities import GoveeLifePlatformEntity
from .utils import GoveeAPI_GetCachedStateValue, async_GoveeAPI_ControlDevice

_LOGGER: Final = logging.getLogger(__name__)
platform = 'humidifier'
platform_device_types = [
    'devices.types.humidifier',
    'devices.types.dehumidifier'
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the humidifier platform."""
    _LOGGER.debug("Setting up %s platform entry: %s | %s", platform, DOMAIN, entry.entry_id)
    entities = []
        
    try:
        _LOGGER.debug("%s - async_setup_entry %s: Getting cloud devices from data store", entry.entry_id, platform)
        entry_data = hass.data[DOMAIN][entry.entry_id]
        api_devices = entry_data[CONF_DEVICES]
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry %s: Getting cloud devices from data store failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
        return False

    for device_cfg in api_devices:
        try:
            if device_cfg.get('type', STATE_UNKNOWN) not in platform_device_types:
                continue      
            device = device_cfg.get('device')
            _LOGGER.debug("%s - async_setup_entry %s: Setup device: %s", entry.entry_id, platform, device) 
            coordinator = entry_data[CONF_COORDINATORS][device]
            entity = GoveeLifeHumidifier(hass, entry, coordinator, device_cfg, platform=platform)
            entities.append(entity)
            await asyncio.sleep(0)
        except Exception as e:
            _LOGGER.error("%s - async_setup_entry %s: Setup device failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
            return False

    _LOGGER.info("%s - async_setup_entry: setup %s %s entities", entry.entry_id, len(entities), platform)
    if not entities:
        return None
    async_add_entities(entities)


class GoveeLifeHumidifier(HumidifierEntity, GoveeLifePlatformEntity):
    """Humidifier class for Govee Life integration."""

    _state_mapping = {}
    _state_mapping_set = {}
    _attr_available_modes = []
    _attr_preset_modes_mapping = {}
    _attr_preset_modes_mapping_set = {}

    def _init_platform_specific(self, **kwargs):
        """Platform specific initialization actions."""
        _LOGGER.debug("%s - %s: _init_platform_specific", self._api_id, self._identifier)
        self.device_class = self._device_cfg.get('type', [])
        if self.device_class == "devices.types.humidifier":
            self._attr_device_class = HumidifierDeviceClass.HUMIDIFIER
        elif self.device_class == "devices.types.dehumidifier":
            self._attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER

        capabilities = self._device_cfg.get('capabilities', [])

        _LOGGER.debug("%s - %s: _init_platform_specific: processing devices request capabilities", self._api_id, self._identifier)
        for cap in capabilities:
            _LOGGER.debug("%s - %s: _init_platform_specific: processing cap: %s", self._api_id, self._identifier, cap)
            if cap['type'] == 'devices.capabilities.on_off':
                for option in cap['parameters']['options']:
                    if option['name'] == 'on':
                        self._state_mapping[option['value']] = STATE_ON
                        self._state_mapping_set[STATE_ON] = option['value']
                    elif option['name'] == 'off':
                        self._state_mapping[option['value']] = STATE_OFF
                        self._state_mapping_set[STATE_OFF] = option['value']
                    else:
                        _LOGGER.warning("%s - %s: _init_platform_specific: unhandled cap option: %s -> %s", self._api_id, self._identifier, cap['type'], option)
            elif cap['type'] == 'devices.capabilities.work_mode':
                self._attr_supported_features |= HumidifierEntityFeature.MODES
                for capFieldWork in cap['parameters']['fields']:
                    if capFieldWork['fieldName'] == 'workMode':
                        for workOption in capFieldWork.get('options', []):
                            self._attr_preset_modes_mapping[workOption['name']] = workOption['value']
                    elif capFieldWork['fieldName'] == 'modeValue':
                        for valueOption in capFieldWork.get('options', []):
                            if valueOption['name'] == 'Manual':
                                for gearOption in valueOption.get('options', []):
                                    self._attr_available_modes.append(gearOption['name'])
                                    self._attr_preset_modes_mapping_set[gearOption['name']] = { "workMode" : self._attr_preset_modes_mapping[valueOption['name']], "modeValue" : gearOption['value'] }
                                    _LOGGER.debug("Adding PRESET mode of %s: %s", gearOption['name'], self._attr_preset_modes_mapping_set[gearOption['name']])
                            elif valueOption['name'] != 'Custom':
                                self._attr_available_modes.append(valueOption['name'])
                                
                                # Handle different value structures for different modes
                                # The original code assumed each work mode had exactly one discrete 'value' field,
                                # but some devices return different structures:
                                #
                                # Example from H7160 dehumidifier:
                                # - Discrete value: {'name': 'gearMode', 'options': [{'name': 'Low', 'value': 1}, ...]}
                                # - Range value: {'name': 'Auto', 'range': {'min': 80, 'max': 80}}
                                # - Default value: {'defaultValue': 0, 'name': 'Dryer'}
                                #
                                # This causes KeyError: 'value' when accessing valueOption['value'] blindly.
                                #
                                # Current fix: Map each work mode to ONE preset with an arbitrarily chosen value
                                # - For 'value': use as-is
                                # - For 'defaultValue': use as-is  
                                # - For 'range': arbitrarily pick the minimum
                                #
                                # TODO: Better solutions could include:
                                # 1. For ranges, create multiple presets (e.g., "Auto 30%", "Auto 50%", "Auto 80%")
                                # 2. Expose a separate humidity target control when in Auto mode
                                # 3. Use the range to set min/max constraints on a slider control
                                # 4. Query the device's current modeValue when in that mode and use it
                                
                                mode_value = None
                                if 'value' in valueOption:
                                    mode_value = valueOption['value']
                                elif 'defaultValue' in valueOption:
                                    mode_value = valueOption['defaultValue']
                                elif 'range' in valueOption:
                                    # For Auto mode with range, use the min value
                                    mode_value = valueOption['range'].get('min', 0)
                                else:
                                    _LOGGER.warning("%s - %s: No value found for mode %s, using 0", self._api_id, self._identifier, valueOption['name'])
                                    mode_value = 0
                                
                                self._attr_preset_modes_mapping_set[valueOption['name']] = { "workMode" : self._attr_preset_modes_mapping[valueOption['name']], "modeValue" : mode_value }
            elif cap['type'] == 'devices.capabilities.range' and cap['instance'] == 'humidity':
                self._attr_min_humidity = cap['parameters']['range']['min']
                self._attr_max_humidity = cap['parameters']['range']['max']
            else:
                _LOGGER.debug("%s - %s: _init_platform_specific: cap unhandled: %s", self._api_id, self._identifier, cap)

    @property
    def current_humidity(self) -> float:
        """Return current humidity."""
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.range', 'humidity')
        # XXX (2025-05-26): The above seems to sometimes return ''
        if value in (None, ''):
            return None
        return float(value)

    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.on_off', 'powerSwitch')
        state = self._state_mapping.get(value, STATE_UNKNOWN)
        return state == STATE_ON

    @property
    def mode(self) -> str | None:
        """Return current mode."""
        return MODE_AUTO

    async def async_turn_on(self, speed: str = None, mode: str = None, **kwargs) -> None:
        """Async: Turn entity on"""
        try:
            _LOGGER.debug("%s - %s: async_turn_on: kwargs = %s", self._api_id, self._identifier, kwargs)
            if not self.is_on:
                state_capability = {
                    "type": "devices.capabilities.on_off",
                    "instance": 'powerSwitch',
                    "value": self._state_mapping_set[STATE_ON]
                }
                if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
                    self.async_write_ha_state()
            else:
                _LOGGER.debug("%s - %s: async_turn_on: device already on", self._api_id, self._identifier)
        except Exception as e:
            _LOGGER.error("%s - %s: async_turn_on failed: %s (%s.%s)", self._api_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)

    async def async_turn_off(self, **kwargs) -> None:
        """Async: Turn entity off"""
        try:
            _LOGGER.debug("%s - %s: async_turn_off: kwargs = %s", self._api_id, self._identifier, kwargs)
            if self.is_on:
                state_capability = {
                    "type": "devices.capabilities.on_off",
                    "instance": 'powerSwitch',
                    "value": self._state_mapping_set[STATE_OFF]
                }
                if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
                    self.async_write_ha_state()
            else:
                _LOGGER.debug("%s - %s: async_turn_on: device already off", self._api_id, self._identifier)
        except Exception as e:
            _LOGGER.error("%s - %s: async_turn_off failed: %s (%s.%s)", self._api_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)

    async def async_set_mode(self, mode: str) -> None:
        """Set new target preset mode."""
        state_capability = {
            "type": "devices.capabilities.work_mode",
            "instance": "workMode",
            "value": self._attr_preset_modes_mapping_set[mode]
        }
        if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
            self.async_write_ha_state()
