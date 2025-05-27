"""Govee API client using Pydantic models."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Final, Optional

import aiohttp
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .cache import GoveeStateCache
from .const import (
    CLOUD_API_HEADER_KEY,
    CLOUD_API_URL_OPENAPI,
    CONF_API_COUNT,
    DOMAIN,
    STATE_DEBUG_FILENAME,
)
from .error_handling import handle_api_errors, log_errors
from .models import (
    Capability,
    CapabilityType,
    Device,
    DeviceControlPayload,
    DeviceControlRequest,
    DeviceControlResponse,
    DevicesResponse,
    DeviceStatePayload,
    DeviceStateRequest,
    DeviceStateResponse,
    create_on_off_capability,
    create_range_capability,
    create_work_mode_capability,
)

_LOGGER: Final = logging.getLogger(__name__)


class GoveeApiClient:
    """Client for interacting with Govee API."""

    def __init__(self, hass: HomeAssistant, entry_id: str):
        """Initialize the API client."""
        self.hass = hass
        self.entry_id = entry_id
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache = GoveeStateCache(hass, entry_id)

    @property
    def entry_data(self) -> dict[str, Any]:
        """Get entry data from hass."""
        return self.hass.data[DOMAIN][self.entry_id]

    @property
    def api_key(self) -> str:
        """Get API key from entry data."""
        return self.entry_data[CONF_API_KEY]

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure we have an active session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    @log_errors(return_value={})
    async def _request(
        self, method: str, endpoint: str, data: str | None = None
    ) -> dict[str, Any]:
        """Make HTTP request to Govee API."""
        url = f"{CLOUD_API_URL_OPENAPI}{endpoint}"
        headers = {CLOUD_API_HEADER_KEY: self.api_key}

        # Increment daily API call counter.
        today = str(date.today())
        api_count = self.entry_data.setdefault(CONF_API_COUNT, {})
        api_count[today] = api_count.get(today, 0) + 1
        _LOGGER.debug(f"{self.entry_id} - API count {today}: {api_count[today]}")

        session = await self._ensure_session()

        async with session.request(method, url, headers=headers, data=data) as response:
            text = await response.text()
            if response.status != 200:
                _LOGGER.error(
                    f"{method} {endpoint} failed: HTTP {response.status} - {text}"
                )
                if method == "POST":
                    return {"code": response.status, "msg": text}
                return {}
            return json.loads(text)

    async def _get(self, endpoint: str) -> dict[str, Any]:
        """Make GET request to Govee API."""
        return await self._request("GET", endpoint)

    async def _post(self, endpoint: str, data: str) -> dict[str, Any]:
        """Make POST request to Govee API."""
        return await self._request("POST", endpoint, data)

    @log_errors(return_value=[])
    async def get_devices(self) -> list[Device]:
        """Get list of devices from API."""
        if not (response := await self._get("user/devices")):
            return []
        return DevicesResponse(**response).devices

    @handle_api_errors
    async def get_device_state(self, device: Device) -> Optional[DeviceStateResponse]:
        """Get device state from API or debug file."""
        # Check debug file first
        debug_file = Path(__file__).parent / STATE_DEBUG_FILENAME.lstrip("/")
        if debug_file.exists():
            data = json.loads(debug_file.read_text())
            return DeviceStateResponse.model_validate(
                data["data"]["cloud_states"][device.device]
            )

        # Make API request
        request = DeviceStateRequest(
            payload=DeviceStatePayload(sku=device.sku, device=device.device)
        )

        response = await self._post(
            "device/state", request.model_dump_json(by_alias=True)
        )

        if not response or "payload" not in response:
            return None

        state = DeviceStateResponse(**response["payload"])

        # Cache the state
        self._cache[device.device] = state

        return state

    @handle_api_errors
    async def control_device(
        self, device: Device, capability: Capability
    ) -> Optional[DeviceControlResponse]:
        """Control device via API."""
        # Check debug mode
        debug_file = Path(__file__).parent / STATE_DEBUG_FILENAME.lstrip("/")
        if debug_file.is_file():
            _LOGGER.debug("Debug mode - simulating success")
            capability_dict = capability.model_dump(by_alias=True)
            capability_dict["state"] = {"status": "success"}
            return DeviceControlResponse(
                request_id="debug-dummy",
                msg="success",
                code=200,
                capability=capability_dict,
            )

        # Create request
        request = DeviceControlRequest(
            payload=DeviceControlPayload(
                sku=device.sku, device=device.device, capability=capability
            )
        )

        response = await self._post(
            "device/control", request.model_dump_json(by_alias=True)
        )

        if not response:
            return None

        control_resp = DeviceControlResponse(**response)

        # Check for errors
        if control_resp.capability and control_resp.capability.state:
            state = control_resp.capability.state
            if state.status == "failure":
                _LOGGER.error(
                    f"Control failed for {device.device}: "
                    f"{state.error_code} - {state.error_msg}"
                )

        # Update cache on success
        if control_resp.code == 200:
            self._update_device_cache(device, capability)

        return control_resp

    @log_errors()
    def _update_device_cache(self, device: Device, capability: Capability) -> None:
        """Update cached device state after successful control."""
        # Get current cached state
        if not (current_state := self._cache[device.device]):
            return

        # Find and update the matching capability
        for cap in current_state.capabilities:
            if (cap.type, cap.instance) == (capability.type, capability.instance):
                # Update the capability's state with the new value
                cap.state["value"] = capability.value
                break

        # Save updated state back to cache
        self._cache[device.device] = current_state

    def get_cached_state_value(
        self, device_id: str, cap_type: CapabilityType, instance: str
    ) -> Any:
        """Get cached state value for a capability."""
        return self._cache.get_capability_value(device_id, cap_type, instance)

    # Backward compatibility methods
    async def async_get_device_state(self, device_cfg: dict[str, Any]) -> bool:
        """Get device state - backward compatibility wrapper."""
        state = await self.get_device_state(Device(**device_cfg))
        return state is not None

    async def async_control_device(
        self, device_cfg: dict[str, Any], capability_dict: dict[str, Any]
    ) -> bool | dict[str, Any]:
        """Control device - backward compatibility wrapper."""
        device = Device(**device_cfg)

        # Convert dict to Capability
        cap_type = CapabilityType(capability_dict["type"])
        capability = Capability(
            type=cap_type,
            instance=capability_dict["instance"],
            value=capability_dict["value"],
        )

        response = await self.control_device(device, capability)

        if response is None:
            return False

        if response.capability and response.capability.state:
            state = response.capability.state
            if state.status == "failure":
                return {"error_code": state.error_code, "error_msg": state.error_msg}

        return response.code == 200

    def get_cached_state_value_compat(
        self, device_id: str, cap_type_str: str, instance: str
    ) -> Any:
        """Get cached state value - backward compatibility wrapper."""
        cap_type = CapabilityType(cap_type_str)
        return self.get_cached_state_value(device_id, cap_type, instance)


# Backward compatibility functions
async def async_get_device_state(
    hass: HomeAssistant, entry_id: str, device_cfg: dict[str, Any]
) -> bool:
    """Get device state - backward compatibility wrapper."""
    client = GoveeApiClient(hass, entry_id)
    return await client.async_get_device_state(device_cfg)


async def async_control_device(
    hass: HomeAssistant,
    entry_id: str,
    device_cfg: dict[str, Any],
    capability_dict: dict[str, Any],
) -> bool | dict[str, Any]:
    """Control device - backward compatibility wrapper."""
    client = GoveeApiClient(hass, entry_id)
    return await client.async_control_device(device_cfg, capability_dict)


def get_cached_state_value(
    hass: HomeAssistant, entry_id: str, device_id: str, cap_type_str: str, instance: str
) -> Any:
    """Get cached state value - backward compatibility wrapper."""
    client = GoveeApiClient(hass, entry_id)
    return client.get_cached_state_value_compat(device_id, cap_type_str, instance)


class GoveeDeviceApiClient:
    """Convenience API client for a specific device."""

    def __init__(self, api_client: GoveeApiClient, device: Device):
        """Initialize device-specific client."""
        self.client = api_client
        self.device = device

    async def control_device(self, capability: Capability) -> bool:
        """Control device with a capability."""
        response = await self.client.control_device(self.device, capability)

        if response and response.capability and response.capability.state:
            state = response.capability.state
            if state.status == "failure":
                raise ValueError(f"API error {state.error_code}: {state.error_msg}")

        return response is not None and response.code == 200

    async def turn_on(self, power_value: int) -> bool:
        """Turn device on."""
        capability = create_on_off_capability(power_value)
        return await self.control_device(capability)

    async def turn_off(self, power_value: int) -> bool:
        """Turn device off."""
        capability = create_on_off_capability(power_value)
        return await self.control_device(capability)

    async def set_work_mode(
        self, work_mode: int, mode_value: Optional[int] = None
    ) -> bool:
        """Set work mode."""
        capability = create_work_mode_capability(work_mode, mode_value)
        return await self.control_device(capability)

    async def set_range_value(self, instance: str, value: float | int) -> bool:
        """Set a range value (humidity, temperature, brightness, etc)."""
        capability = create_range_capability(instance, value)
        return await self.control_device(capability)

    async def update_state(self) -> Optional[DeviceStateResponse]:
        """Update device state from API."""
        return await self.client.get_device_state(self.device)

    def get_cached_value(self, cap_type: CapabilityType, instance: str) -> Any:
        """Get cached capability value."""
        return self.client.get_cached_state_value(
            self.device.device, cap_type, instance
        )

    def get_on_off_value(self) -> Optional[int]:
        """Get cached power state value."""
        return self.get_cached_value(CapabilityType.ON_OFF, "powerSwitch")

    def get_work_mode(self) -> Optional[dict[str, Any]]:
        """Get cached work mode value."""
        return self.get_cached_value(CapabilityType.WORK_MODE, "workMode")

    def get_range_value(self, instance: str) -> Optional[float | int]:
        """Get cached range value."""
        return self.get_cached_value(CapabilityType.RANGE, instance)
