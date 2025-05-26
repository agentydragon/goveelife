"""Sensor entities for the Govee Life integration."""

import logging
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
    STATE_UNKNOWN,
)

from .entities import GoveeLifePlatformEntity
from .const import DOMAIN, CONF_COORDINATORS
from .utils import GoveeAPI_GetCachedStateValue, async_GoveeAPI_ControlDevice

_LOGGER = logging.getLogger(__name__)
PLATFORM = 'fan'
PLATFORM_DEVICE_TYPES = [
    'devices.types.air_purifier',
    'devices.types.fan'
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the fan platform."""
    prefix = f"{entry.entry_id} - async_setup_entry {PLATFORM}: "
    _LOGGER.debug("Setting up %s platform entry: %s | %s", PLATFORM, DOMAIN, entry.entry_id)
    entities = []

    try:
        _LOGGER.debug(f"{prefix}Getting cloud devices from data store")
        entry_data = hass.data[DOMAIN][entry.entry_id]
        api_devices = entry_data.get('devices', [])
    except Exception:
        _LOGGER.error(f"{prefix}Getting cloud devices from data store failed")
        return False

    for device_cfg in api_devices:
        try:
            if device_cfg.get('type', STATE_UNKNOWN) not in PLATFORM_DEVICE_TYPES:
                continue

            device_id = device_cfg.get('device')
            _LOGGER.debug(f"{prefix}Setup device: {device_id}")
            coordinator = entry_data[CONF_COORDINATORS][device_id]
            entity = GoveeLifeFan(hass, entry, coordinator, device_cfg, platform=PLATFORM)
            entities.append(entity)
            await asyncio.sleep(0)
        except Exception:
            _LOGGER.error(f"{prefix}Setup device failed")
            return False

    _LOGGER.info(f"{prefix}setup {len(entities)} {PLATFORM} entities")
    if not entities:
        return None
    async_add_entities(entities)


class GoveeLifeFan(FanEntity, GoveeLifePlatformEntity):
    """Fan class for Govee Life integration."""

    _state_mapping = {}
    _state_mapping_set = {}
    _attr_preset_modes = []
    _attr_preset_modes_mapping = {}
    _attr_preset_modes_mapping_set = {}

    def _init_platform_specific(self, **kwargs):
        """Platform specific initialization actions."""
        prefix = f"{self._api_id} - {self._identifier}: _init_platform_specific"
        _LOGGER.debug(prefix)
        capabilities = self._device_cfg.get('capabilities', [])

        for cap in capabilities:
            if cap['type'] == 'devices.capabilities.on_off':
                self._attr_supported_features |= FanEntityFeature.TURN_ON
                for option in cap['parameters']['options']:
                    if option['name'] == 'on':
                        self._state_mapping[option['value']] = STATE_ON
                        self._state_mapping_set[STATE_ON] = option['value']
                    elif option['name'] == 'off':
                        self._state_mapping[option['value']] = STATE_OFF
                        self._state_mapping_set[STATE_OFF] = option['value']
                    else:
                        _LOGGER.warning(f"{prefix}: unhandled cap option: {cap['type']} -> {option}")
            elif cap['type'] == 'devices.capabilities.work_mode':
                self._attr_supported_features |= FanEntityFeature.PRESET_MODE
                for capFieldWork in cap['parameters']['fields']:
                    if capFieldWork['fieldName'] == 'workMode':
                        for workOption in capFieldWork.get('options', []):
                            self._attr_preset_modes_mapping[workOption['name']] = workOption['value']
                    elif capFieldWork['fieldName'] == 'modeValue':
                        for valueOption in capFieldWork.get('options', []):
                            if valueOption['name'] == 'gearMode':
                                for gearOption in valueOption.get('options', []):
                                    self._attr_preset_modes.append(gearOption['name'])
                                    self._attr_preset_modes_mapping_set[gearOption['name']] = {"workMode": self._attr_preset_modes_mapping[valueOption['name']], "modeValue": gearOption['value']}
                            elif valueOption['name'] != 'Custom':
                                self._attr_preset_modes.append(valueOption['name'])
                                self._attr_preset_modes_mapping_set[valueOption['name']] = {"workMode": self._attr_preset_modes_mapping[valueOption['name']], "modeValue": valueOption['value']}

    @property
    def state(self) -> str | None:
        """Return the current state of the entity."""
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.on_off', 'powerSwitch')
        return self._state_mapping.get(value, STATE_UNKNOWN)

    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        return self.state == STATE_ON

    async def async_turn_on(self, speed: str = None, mode: str = None, **kwargs) -> None:
        """Async: Turn entity on."""
        prefix = f"{self._api_id} - {self._identifier}: async_turn_on"
        try:
            _LOGGER.debug(f"{prefix}: {kwargs=}")
            if not self.is_on:
                state_capability = {
                    "type": "devices.capabilities.on_off",
                    "instance": 'powerSwitch',
                    "value": self._state_mapping_set[STATE_ON]
                }
                if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
                    self.async_write_ha_state()
            else:
                _LOGGER.debug(f"{prefix}: device already on")
        except Exception:
            _LOGGER.error(f"{prefix} failed")

    async def async_turn_off(self, **kwargs) -> None:
        """Async: Turn entity off."""
        prefix = f"{self._api_id} - {self._identifier}: async_turn_off"
        try:
            _LOGGER.debug(f"{prefix}: {kwargs=}")
            if self.is_on:
                state_capability = {
                    "type": "devices.capabilities.on_off",
                    "instance": 'powerSwitch',
                    "value": self._state_mapping_set[STATE_OFF]
                }
                if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
                    self.async_write_ha_state()
            else:
                _LOGGER.debug(f"{prefix}: device already off")
        except Exception:
            _LOGGER.error(f"{prefix} failed")

    @property
    def preset_mode(self) -> str | None:
        """Return the preset_mode of the entity."""
        prefix = f"{self._api_id} - {self._identifier}: preset_mode"
        value = GoveeAPI_GetCachedStateValue(self.hass, self._entry_id, self._device_cfg.get('device'), 'devices.capabilities.work_mode', 'workMode')
        v = {"workMode": value['workMode'], "modeValue": value['modeValue']}
        key_list = [key for key, val in self._attr_preset_modes_mapping_set.items() if val == v]

        if key_list:
            return key_list[0]
        else:
            _LOGGER.warning(f"{prefix}: invalid {v=}")
            _LOGGER.debug(f"{prefix}: valid are: {self._attr_preset_modes_mapping_set=}")
            return STATE_UNKNOWN

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        state_capability = {
            "type": "devices.capabilities.work_mode",
            "instance": "workMode",
            "value": self._attr_preset_modes_mapping_set[preset_mode]
        }
        if await async_GoveeAPI_ControlDevice(self.hass, self._entry_id, self._device_cfg, state_capability):
            self.async_write_ha_state()
