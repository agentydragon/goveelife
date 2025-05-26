"""Helper functions for Govee Life."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import date
from typing import Final

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (ATTR_DATE, CONF_API_KEY, CONF_COUNT,
                                 CONF_PARAMS, CONF_STATE, CONF_TIMEOUT)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (CLOUD_API_HEADER_KEY, CLOUD_API_URL_OPENAPI,
                    CONF_API_COUNT, DOMAIN, STATE_DEBUG_FILENAME)

_LOGGER: Final = logging.getLogger(__name__)


async def async_ProgrammingDebug(obj, show_all: bool = False) -> None:
    """Async: return all attributes of a specific objec"""
    prefix = f"{DOMAIN} - async_ProgrammingDebug: "
    try:
        _LOGGER.debug(f"{prefix}{obj}")
        for attr in dir(obj):
            if attr.startswith("_") and not show_all:
                continue
            if hasattr(obj, attr):
                _LOGGER.debug(f"{prefix}{attr} = {getattr(obj, attr)}")
            await asyncio.sleep(0)
    except Exception:
        _LOGGER.error(f"{prefix}failed")
        pass


def ProgrammingDebug(obj, show_all: bool = False) -> None:
    """return all attributes of a specific objec"""
    prefix = f"{DOMAIN} - ProgrammingDebug: "
    try:
        _LOGGER.debug(f"{prefix}{obj}")
        for attr in dir(obj):
            if attr.startswith("_") and not show_all:
                continue
            if hasattr(obj, attr):
                _LOGGER.debug(f"{prefix}{attr} = {getattr(obj, attr)}")
    except Exception:
        _LOGGER.error(f"{prefix}failed")
        pass


async def async_GooveAPI_CountRequests(hass: HomeAssistant, entry_id: str) -> None:
    """Asnyc: Count daily number of requests to GooveAPI"""
    prefix = f"{entry_id} - async_GooveAPI_CountRequests: "
    try:
        entry_data = hass.data[DOMAIN][entry_id]
        today = date.today()
        # entry_data.setdefault(CONF_API_COUNT, {CONF_COUNT : 0, ATTR_DATE : today})
        v = entry_data.get(CONF_API_COUNT, {CONF_COUNT: 0, ATTR_DATE: today})
        if v[ATTR_DATE] == today:
            v[CONF_COUNT] = int(v[CONF_COUNT]) + 1
        else:
            v[CONF_COUNT] = 1
        entry_data[CONF_API_COUNT] = v

        _LOGGER.debug(f"{prefix}{v[ATTR_DATE]} -> {v[CONF_COUNT]}")
    except Exception:
        _LOGGER.error(f"{prefix}Failed")
        return None


async def async_GoveeAPI_GETRequest(
    hass: HomeAssistant, entry_id: str, path: str
) -> None:
    """Asnyc: Request device list via GooveAPI"""
    prefix = f"{entry_id} - async_GoveeAPI_GETRequest: "
    try:
        debug_file = os.path.dirname(os.path.realpath(__file__)) + STATE_DEBUG_FILENAME
        if os.path.isfile(debug_file):
            _LOGGER.debug(f"{prefix}load debug file: {debug_file}")
            with open(debug_file, "r") as stream:
                payload = json.load(stream)
                return payload["data"]["cloud_devices"]
    except Exception:
        _LOGGER.error(f"{prefix}debug file load failed")
        return None

    try:
        _LOGGER.debug(f"{prefix}perform api request")
        entry_data = hass.data[DOMAIN][entry_id]

        # _LOGGER.debug(f"{prefix}perpare parameters for GET request"
        headers = {
            "Content-Type": "application/json",
            CLOUD_API_HEADER_KEY: str(entry_data[CONF_PARAMS].get(CONF_API_KEY, None)),
        }
        timeout = entry_data[CONF_PARAMS].get(CONF_TIMEOUT, None)
        url = CLOUD_API_URL_OPENAPI + "/" + path.strip("/")

        # _LOGGER.debug(f"{prefix}extecute GET request"
        await async_GooveAPI_CountRequests(hass, entry_id)
        r = await hass.async_add_executor_job(
            lambda: requests.get(url, headers=headers, timeout=timeout)
        )
        if r.status_code == 429:
            _LOGGER.error(f"{prefix}Too many API request - limit is 10000/Account/Day")
            return None
        elif r.status_code == 401:
            _LOGGER.error(f"{prefix}Unauthorize - check you APIKey")
            return None
        elif not r.status_code == 200:
            _LOGGER.error(f"{prefix}Failed: {r.text}")
            return None

        _LOGGER.debug(f"{prefix}convert resulting json to object")
        return json.loads(r.text)["data"]

    except Exception:
        _LOGGER.error(f"{prefix}Failed")
        return None


async def async_GoveeAPI_POSTRequest(
    hass: HomeAssistant, entry_id: str, path: str, data: str, return_status_code=False
) -> None:
    """Asnyc: Perform post state request / control request via GooveAPI"""
    prefix = "%s - async_GoveeAPI_POSTRequest: " % entry_id
    try:
        # _LOGGER.debug(f"{prefix}perform api request")
        entry_data = hass.data[DOMAIN][entry_id]

        # _LOGGER.debug(f"{prefix}perpare parameters for POST request"
        headers = {
            "Content-Type": "application/json",
            CLOUD_API_HEADER_KEY: str(entry_data[CONF_PARAMS].get(CONF_API_KEY, None)),
        }
        timeout = entry_data[CONF_PARAMS].get(CONF_TIMEOUT, None)
        data = re.sub("<dynamic_uuid>", str(uuid.uuid4()), data)
        _LOGGER.debug(f"{prefix}{data = }")
        data = json.loads(data)
        url = CLOUD_API_URL_OPENAPI + "/" + path.strip("/")

        # _LOGGER.debug(f"{prefix}extecute POST request"
        await async_GooveAPI_CountRequests(hass, entry_id)
        r = await hass.async_add_executor_job(
            lambda: requests.post(url, json=data, headers=headers, timeout=timeout)
        )
        if r.status_code == 429:
            _LOGGER.error(f"{prefix}Too many API request - limit is 10000/Account/Day")
            if return_status_code == True:
                return r.status_code
            return None
        elif r.status_code == 401:
            _LOGGER.error(f"{prefix}Unauthorize - check you APIKey")
            if return_status_code == True:
                return r.status_code
            return None
        elif r.status_code != 200:
            _LOGGER.error(f"{prefix}Failed {r.status_code=}: {r.text}")
            if return_status_code == True:
                return r.status_code
            return None

        # _LOGGER.debug(f"{prefix}convert resulting json to object")
        return r.json()

    except Exception:
        _LOGGER.error(f"{prefix}Failed")
        return None


async def async_GoveeAPI_GetDeviceState(
    hass: HomeAssistant, entry_id: str, device_cfg, return_status_code=False
) -> None:
    """Asnyc: Request and save state of device via GooveAPI"""
    prefix = f"{entry_id} - async_GoveeAPI_GetDeviceState: "
    try:
        # _LOGGER.debug(f"{prefix}preparing values")
        entry_data = hass.data[DOMAIN][entry_id]
        json_str = json.dumps(
            {
                "requestId": "<dynamic_uuid>",
                "payload": {
                    "sku": str(device_cfg.get("sku")),
                    "device": str(device_cfg.get("device")),
                },
            }
        )
        r = None
    except Exception:
        _LOGGER.error(f"{prefix}preparing values failed")
        return False

    try:
        debug_file = os.path.dirname(os.path.realpath(__file__)) + STATE_DEBUG_FILENAME
        if os.path.isfile(debug_file):
            _LOGGER.debug(f"{prefix}load debug file: {debug_file}")
            with open(debug_file, "r") as stream:
                payload = json.load(stream)
                r = payload["data"]["cloud_states"][device_cfg.get("device")]
    except Exception:
        _LOGGER.error(f"{prefix}debug file load failed")
        return False

    try:
        if r is None:
            r = await async_GoveeAPI_POSTRequest(
                hass, entry_id, "device/state", json_str, return_status_code
            )
            r = r["payload"]
        _LOGGER.debug(f"{prefix}r = {r}")
        if isinstance(r, int) and return_status_code == True:
            return r
        if not isinstance(r, int):
            entry_data.setdefault(CONF_STATE, {})
            d = device_cfg.get("device")
            entry_data[CONF_STATE][d] = r
            return True
        return False

    except Exception:
        _LOGGER.error(f"{prefix}Failed")
        return False


async def async_GoveeAPI_ControlDevice(
    hass: HomeAssistant,
    entry_id: str,
    device_cfg,
    state_capability,
    return_status_code=False,
) -> None:
    """Asnyc: Trigger device action via GooveAPI"""
    prefix = "%s - async_GoveeAPI_ControlDevice: " % entry_id
    try:
        # _LOGGER.debug("{prefix}preparing values")
        entry_data = hass.data[DOMAIN][entry_id]
        state_capability_json = json.dumps(state_capability)
        json_str = json.dumps(
            {
                "requestId": "<dynamic_uuid>",
                "payload": {
                    "sku": device_cfg.get("sku"),
                    "device": str(device_cfg.get("device")),
                    "capability": state_capability,
                },
            }
        )
        _LOGGER.debug(f"{prefix}{json_str = }")
        r = None
    except Exception:
        _LOGGER.error(f"{prefix}preparing values failed")
        return False

    try:
        debug_file = os.path.dirname(os.path.realpath(__file__)) + STATE_DEBUG_FILENAME
        if os.path.isfile(debug_file):
            _LOGGER.debug(f"{prefix}create debug reply")
            state_capability["state"] = {"status": "success"}
            r = {"requestId": "debug-dummy", "msg": "success", "code": 200, "capability": state_capability}
    except Exception:
        _LOGGER.error(f"{prefix}debug reply failed")
        return False

    try:
        if r is None:
            r = await async_GoveeAPI_POSTRequest(
                hass, entry_id, "device/control", json_str, return_status_code
            )
        _LOGGER.debug(f"{prefix}r = {r}")
        if isinstance(r, int) and return_status_code == True:
            return r
        if not isinstance(r, int) and not r.get("capability", None) is None:
            # Extract capability once to avoid repetition
            capability = r["capability"]
            state = capability.get("state", {})
            status = state.get("status", "")

            if status == "failure":
                error_code = state.get("errorCode", "Unknown")
                error_msg = state.get("errorMsg", "Unknown error")
                _LOGGER.error(f"{prefix}API returned error: {error_code} - {error_msg}")
                # Return error details for upstream handling
                return {"error_code": error_code, "error_msg": error_msg}

            # Only update state if the command was successful
            entry_data.setdefault(CONF_STATE, {})
            d = device_cfg.get("device")

            # Move value into state for consistency
            v = capability.pop("value")
            capability["state"] = {"value": v}

            # Find and update the matching capability
            for cap in entry_data[CONF_STATE][d]["capabilities"]:
                if (
                    cap["type"] == capability["type"]
                    and cap["instance"] == capability["instance"]
                ):
                    entry_data[CONF_STATE][d]["capabilities"].remove(cap)
                    entry_data[CONF_STATE][d]["capabilities"].append(capability)
                    _LOGGER.debug(f"{prefix}updated old capability state: {cap}")
                    _LOGGER.debug(f"{prefix}with new capability state: {capability}")
                    return True
        else:
            _LOGGER.warning(f"{prefix}unhandled api return = {r}")
        return False

    except Exception:
        _LOGGER.error(f"{prefix}Failed")
        return False


def GoveeAPI_GetCachedStateValue(
    hass: HomeAssistant, entry_id: str, device_id, value_type, value_instance
):
    """Asnyc: Get value of a state from local cache"""
    prefix = f"{entry_id} - GoveeAPI_GetCachedStateValue: "
    try:
        # _LOGGER.debug(f"{prefix}preparing values")
        entry_data = hass.data[DOMAIN][entry_id]
        capabilities = ((entry_data.get(CONF_STATE)).get(device_id)).get(
            "capabilities", []
        )
        value = None
    except Exception:
        _LOGGER.error(f"{prefix}Failed")
        return None

    try:
        # _LOGGER.debug(f"{prefix}getting value: {value_type} - {value_instance}")
        for cap in capabilities:
            if cap["type"] == value_type and cap["instance"] == value_instance:
                cap_state = cap.get("state", None)
                if not cap_state == None:
                    value = cap_state.get("value", cap_state.get(value_instance, None))
        # _LOGGER.debug(f"{prefix}value: {value_instance} = {value}")
        return value
    except Exception:
        _LOGGER.error(f"{prefix}Failed")
        return None
