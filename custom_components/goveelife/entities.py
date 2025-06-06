"""Base entities for the Govee Life integration."""

from __future__ import annotations
from typing import Final
import logging
from datetime import timedelta
from pathlib import Path

import async_timeout

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import (
    DeviceInfo,
    Entity,
    generate_entity_id,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_PARAMS,
    CONF_SCAN_INTERVAL,
    CONF_STATE,
    CONF_TIMEOUT,
    STATE_UNKNOWN,
)

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    STATE_DEBUG_FILENAME,
)

from .api import GoveeApiClient
from .models import Device

_LOGGER: Final = logging.getLogger(__name__)


class GoveeLifePlatformEntity(CoordinatorEntity, Entity):
    """Base class for Govee Life integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator,
        device_cfg,
        platform: str = "entities",
        **kwargs,
    ) -> None:
        """Initialize the entity."""
        try:
            self._api_id = str(entry.data.get(CONF_FRIENDLY_NAME, DEFAULT_NAME))
            self._identifier = (
                str(device_cfg.get("device")).replace(":", "") + "_" + platform
            ).lower()

            prefix = f"{self._api_id} - {self._identifier}: __init__"
            _LOGGER.debug(prefix)
            self._device_cfg = device_cfg
            self._entry = entry
            self._entry_id = self._entry.entry_id
            self.hass = hass

            self._name = self._device_cfg.get("deviceName")

            # self._icon = None
            # self._device_class = None
            # self._unit_of_measurement = None
            # self._entity_category = None

            self._entity_id = self._name.lower()
            self.uniqueid = self._identifier + "_" + self._entity_id

            self._attributes = {}
            # self._attributes['description'] = self._entity_cfg.get('description', None)
            self._state = STATE_UNKNOWN

            super().__init__(coordinator)

            # _LOGGER.debug("%s - %s: __init__ kwargs = %s", self._api_id, self._identifier, kwargs)
            self._init_platform_specific(**kwargs)
            self.entity_id = generate_entity_id(
                platform + ".{}", self._entity_id, hass=hass
            )
            _LOGGER.debug(f"{prefix} complete ({self.uniqueid=})")
            # ProgrammingDebug(self,True)
        except Exception:
            _LOGGER.error(f"{prefix} failed")
            return None

    def _init_platform_specific(self, **kwargs):
        """Platform specific init actions"""
        # do nothing here as this is only a drop-in option for other platforms
        # do not put actions in a try / except block - execeptions should be covered by __init__
        pass

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self._name

    #    @property
    #    def description(self) -> str | None:
    #        """Return the description of the entity."""
    #        return self._description

    #    @property
    #    def icon(self) -> str | None:
    #        """Return the icon of the entity"""
    #        return self._icon

    #    @property
    #    def device_class(self) -> str | None:
    #        """Return the device_class of the entity."""
    #        return self._device_class

    #    @property
    #    def unit_of_measurement(self) -> str | None:
    #        """Return the unit_of_measurement of the entity."""
    #        return self._unit_of_measurement

    #    @property
    #    def entity_category(self) -> EntityCategory | None:
    #        """Return the entity_category of the entity."""
    #        return None

    @property
    def state(self) -> str | None:
        """Return the current state of the entity."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        return self._attributes

    @property
    def unique_id(self) -> str | None:
        """Return the unique identifier for this entity."""
        return self.uniqueid

    @property
    def available(self) -> bool:
        """Return if device is available."""
        # _LOGGER.debug("%s - %s: available", self._api_id, self._identifier)
        try:
            entry_data = self.hass.data[DOMAIN][self._entry_id]
            d = self._device_cfg.get("device")
            capabilities = entry_data[CONF_STATE][d].get("capabilities", [])
            value = False
            for cap in capabilities:
                if cap["type"] == "devices.capabilities.online":
                    cap_state = cap.get("state", None)
                    if cap_state is not None:
                        value = cap_state.get("value", False)
            # _LOGGER.debug("%s - %s: available result: %s", self._api_id, self._identifier, value)
            return value
        except Exception:
            _LOGGER.error("%s - available: Failed", self._entry_id)
            return False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for device registry."""
        # _LOGGER.debug("%s - %s: device_info", self._api_id, self._identifier)
        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_cfg.get("device", None))},
            manufacturer=DOMAIN,
            model=self._device_cfg.get("sku", STATE_UNKNOWN),
            name=self._device_cfg.get("deviceName", STATE_UNKNOWN),
            hw_version=str(self._device_cfg.get("type", STATE_UNKNOWN)).split(".")[-1],
        )
        # _LOGGER.debug("%s - %s: device_info result: %s", self._api_id, self._identifier, info)
        return info

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # _LOGGER.debug("%s - %s: _handle_coordinator_update: new state: %s", self._api_id, self._identifier, s)
        self.async_write_ha_state()


class GoveeAPIUpdateCoordinator(DataUpdateCoordinator):
    """State update coordinator for GoveeAPI."""

    def __init__(self, hass, entry_id, device_cfg):
        """Initialize the coordinator."""
        self._identifier = (
            str(device_cfg["device"]).replace(":", "")
        ) + "_GoveeAPIUpdate"
        prefix = f"{self._identifier} - async_GoveeAPI_GetDeviceState: __init__"
        _LOGGER.debug(prefix)
        scan_interval = hass.data[DOMAIN][entry_id][CONF_PARAMS][CONF_SCAN_INTERVAL]
        super().__init__(
            hass,
            _LOGGER,
            name=self._identifier,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._entry_id = entry_id
        self._device_cfg = device_cfg

    async def _async_update_data(self):
        """Fetch data from the API endpoint."""
        prefix = f"{self._entry_id} - GoveeAPIUpdateCoordinator: _async_update_data"
        try:
            entry_data = self.hass.data[DOMAIN][self._entry_id]
            api_client = GoveeApiClient(self.hass, self._entry_id)
            device = Device(**self._device_cfg)
            async with async_timeout.timeout(entry_data[CONF_PARAMS][CONF_TIMEOUT]):
                result = await api_client.get_device_state(device)
        except Exception:
            _LOGGER.error(f"{prefix} Failed")
            return False

        try:
            scan_interval = entry_data.get(CONF_SCAN_INTERVAL)
            debug_file = Path(__file__).parent / STATE_DEBUG_FILENAME.lstrip("/")
            if debug_file.is_file() and scan_interval is None:
                scan_interval = 3600
                _LOGGER.info(
                    f"{prefix}: debug poll interval is {scan_interval=} seconds"
                )

            if scan_interval is not None:
                scan_interval = timedelta(seconds=scan_interval)
                if scan_interval != self.update_interval:
                    self.update_interval = scan_interval
        except Exception:
            _LOGGER.warning(f"{prefix} update interval change failed")

        if result == 429 or result == 401:
            raise ConfigEntryAuthFailed("Authentication failed")
