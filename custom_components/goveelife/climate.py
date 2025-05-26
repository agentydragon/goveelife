"""Sensor entities for the Govee Life integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    CONF_DEVICES,
    STATE_UNKNOWN,
    UnitOfTemperature,
)

from .entities import GoveeLifePlatformEntity
from .const import DOMAIN, CONF_COORDINATORS
from .utils import GoveeAPI_GetCachedStateValue, async_GoveeAPI_ControlDevice

_LOGGER: Final = logging.getLogger(__name__)
PLATFORM = 'climate'
PLATFORM_DEVICE_TYPES = [
    'devices.types.heater',
    'devices.types.kettle',
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the climate platform."""
    prefix = f"{entry.entry_id} - async_setup_entry {PLATFORM}: "
    _LOGGER.debug("Setting up %s platform entry: %s | %s", PLATFORM, DOMAIN, entry.entry_id)
    entities = []

    try:
        entry_data = hass.data[DOMAIN][entry.entry_id]
        api_devices = entry_data[CONF_DEVICES]
    except Exception:
        _LOGGER.error(f"{prefix}Failed to get cloud devices from data store")
        return

    for device_cfg in api_devices:
        try:
            if device_cfg.get('type') not in PLATFORM_DEVICE_TYPES:
                continue
            device = device_cfg.get('device')
            coordinator = entry_data[CONF_COORDINATORS][device]
            entity = GoveeLifeClimate(hass, entry, coordinator, device_cfg, platform=PLATFORM)
            entities.append(entity)
            await asyncio.sleep(0)
        except Exception:
            _LOGGER.error(f"{prefix}Failed to setup device")
            return

    if entities:
        async_add_entities(entities)


class GoveeLifeClimate(ClimateEntity, GoveeLifePlatformEntity):
    """Climate class for Govee Life integration."""

    _attr_hvac_modes = []
    _attr_hvac_modes_mapping = {}
    _attr_hvac_modes_mapping_set = {}
    _attr_preset_modes = []
    _attr_preset_modes_mapping = {}
    _attr_preset_modes_mapping_set = {}
    _enable_turn_on_off_backwards_compatibility = False

    def _init_platform_specific(self, **kwargs):
        """Platform specific init actions."""
        prefix = f"{self._api_id} - {self._identifier}: _init_platform_specific"
        _LOGGER.debug(prefix)
        capabilities = self._device_cfg.get('capabilities', [])

        _LOGGER.debug(f"{prefix}: processing devices request capabilities")
        for cap in capabilities:
            #_LOGGER.debug("%s - %s: _init_platform_specific: processing cap: %s", self._api_id, self._identifier, cap)
            if cap['type'] == 'devices.capabilities.on_off':
                for option in cap['parameters']['options']:
                    if option['name'] == 'on':
                        self._attr_supported_features |= ClimateEntityFeature.TURN_ON
                        self._attr_hvac_modes.append(HVACMode.HEAT_COOL)
                        self._attr_hvac_modes_mapping[option['value']] = HVACMode.HEAT_COOL
                        self._attr_hvac_modes_mapping_set[HVACMode.HEAT_COOL] = option['value']
                    elif option['name'] == 'off':
                        self._attr_supported_features |= ClimateEntityFeature.TURN_OFF
                        self._attr_hvac_modes.append(HVACMode.OFF)
                        self._attr_hvac_modes_mapping[option['value']] = HVACMode.OFF
                        self._attr_hvac_modes_mapping_set[HVACMode.OFF] = option['value']
                    else:
                        _LOGGER.warning(f"{prefix}: unknown on_off option: {option}")
            elif cap['type'] == 'devices.capabilities.temperature_setting' and (cap['instance'] in ['targetTemperature', 'sliderTemperature']):
                self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
                for field in cap['parameters']['fields']:
                    if field['fieldName'] == 'temperature':
                        self._attr_max_temp = field['range']['max']
                        self._attr_min_temp = field['range']['min']
                        self._attr_target_temperature_step = field['range']['precision']
                    elif field['fieldName'] == 'unit':
                        self._attr_temperature_unit = UnitOfTemperature[field['defaultValue'].upper()]
                    elif field['fieldName'] == 'autoStop':
                        pass #TO-BE-DONE: implement as switch entity type
            elif cap['type'] == 'devices.capabilities.work_mode':
                self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
                for capFieldWork in cap['parameters']['fields']:
                    if not capFieldWork['fieldName'] == 'workMode':
                        continue
                    # Clear any existing modes to prevent duplicates
                    self._attr_preset_modes = []
                    self._attr_preset_modes_mapping = {}
                    self._attr_preset_modes_mapping_set = {}

                    for workOption in capFieldWork.get('options', []):
                        if workOption['name'] not in self._attr_preset_modes:
                            self._attr_preset_modes.append(workOption['name'])
                            self._attr_preset_modes_mapping[workOption['name']] = workOption['value']
                            # Get the temperature value for this mode
                            mode_value = 0
                            for field in cap['parameters']['fields']:
                                if field['fieldName'] == 'modeValue' and 'defaultValue' in field:
                                    mode_value = field['defaultValue']
                            self._attr_preset_modes_mapping_set[workOption['name']] = {
                                'workMode': workOption['value'],
                                'modeValue': mode_value,
                            }
            elif cap['type'] == 'devices.capabilities.property' and cap['instance'] == 'sensorTemperature':
                pass #do nothing as this is handled within 'current_temperature' property
            else:
                _LOGGER.debug(f"{prefix}: cap unhandled: {cap=}")

    @property
    def hvac_mode(self) -> str:
        """Return the hvac_mode of the entity."""
        prefix = f"{self._api_id} - {self._identifier}: hvac_mode"
        #_LOGGER.debug(prefix)  
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.on_off', 'powerSwitch')
        v = self._attr_hvac_modes_mapping.get(value,STATE_UNKNOWN)
        if v == STATE_UNKNOWN:
            _LOGGER.warning(f"{prefix}: invalid {value=}")
            _LOGGER.debug(f"{prefix}: valid are: {self._state_mapping=}")
        return v

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        #_LOGGER.debug("%s - %s: async_set_hvac_mode", self._api_id, self._identifier) 
        state_capability = {
            "type": "devices.capabilities.on_off",
            "instance": "powerSwitch",
            "value": self._attr_hvac_modes_mapping_set[hvac_mode]
            }
        if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
            self.async_write_ha_state()
        return None

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEATING)

    @property
    def preset_mode(self) -> str | None:
        """Return the preset_mode of the entity."""
        #_LOGGER.debug("%s - %s: preset_mode", self._api_id, self._identifier)  
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.work_mode', 'workMode')
        if value is None:
            return None
        work_mode = value.get("workMode")
        if work_mode is None:
            return None

        # Find the preset mode name that matches this workMode value
        for preset_name, preset_value in self._attr_preset_modes_mapping.items():
            if preset_value == work_mode:
                return preset_name

        return None

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set new target preset mode."""
        #_LOGGER.debug("%s - %s: async_set_preset_mode", self._api_id, self._identifier)
        state_capability = {
            "type": "devices.capabilities.work_mode",
            "instance": "workMode",
            "value": self._attr_preset_modes_mapping_set[preset_mode]
            }
        if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
            self.async_write_ha_state()
        return None
    

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit of the entity."""
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.temperature_setting', 'targetTemperature')
        if value is not None:
            return UnitOfTemperature[value.get("unit", "CELSIUS").upper()]

        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.temperature_setting', 'sliderTemperature')
        if value is not None:
            return UnitOfTemperature[value.get("unit", "CELSIUS").upper()]

        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature of the entity."""
        prefix = f"{self._api_id} - {self._identifier}: target_temperature: "
        # First try to get the temperature from the current preset mode
        preset_mode = self.preset_mode
        _LOGGER.debug(f"{prefix}{preset_mode=}")

        if preset_mode and preset_mode in self._attr_preset_modes_mapping_set:
            mode_value = self._attr_preset_modes_mapping_set[preset_mode].get("modeValue")
            _LOGGER.debug(f"{prefix}{mode_value=}")
            if mode_value is not None and mode_value != 0:
                return float(mode_value)

        # If no preset mode temperature, try to get it from the slider
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.temperature_setting', 'sliderTemperature')
        _LOGGER.debug(f"{prefix}{value=}")
        if value is None:
            return None
        temperature = value.get("targetTemperature")
        if temperature is None:
            return None
        return float(temperature)

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""        
        #_LOGGER.debug("%s - %s: async_set_temperature", self._api_id, self._identifier)
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.temperature_setting', 'targetTemperature')
        unit = value.get('unit', 'Celsius')
        state_capability = {
            "type": "devices.capabilities.temperature_setting",
            "instance": "targetTemperature",
            "value": {
                "temperature": kwargs['temperature'],
                "unit": unit,
                }
            }
        if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
            self.async_write_ha_state()      
        return None


    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature of the entity."""
        #_LOGGER.debug("%s - %s: current_temperature", self._api_id, self._identifier)  
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.property', 'sensorTemperature')
        if value is None or value == "":
            return None
        if self.temperature_unit == UnitOfTemperature.CELSIUS:
            #value seems to be always Fahrenheit - calculate to °C if necessary
            value = (float(value) - 32) * 5 / 9
        return float(value)


