# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Home Assistant custom integration for Govee smart home devices using their API v2.0. It's a cloud-polling integration that supports various device types including lights, heaters, air purifiers, fans, ice makers, diffusers, and sockets.

## Architecture

### Core Components

- **Entry Point**: `__init__.py` - Orchestrates setup, update coordinators, and platform forwarding
- **Config Flow**: `config_flow.py` - Handles user setup with API key authentication
- **Update Coordinator**: `GoveeAPIUpdateCoordinator` in `entities.py` - Manages periodic device state polling (default 60s)
- **API Layer**: `utils.py` - Contains all Govee API v2 communication logic
- **Platform Modules**: Each device type has its own module (e.g., `light.py`, `fan.py`, `climate.py`)

### Key Design Patterns

1. **Platform-based Architecture**: Each device type inherits from `GoveeLifePlatformEntity` base class
2. **Coordinator Pattern**: Uses Home Assistant's `DataUpdateCoordinator` for efficient API polling
3. **State Caching**: Device states cached in `hass.data[DOMAIN][entry_id][CONF_STATE]`
4. **Debug Mode**: Supports `/_diagnostics.json` file for local testing without API calls
5. **Rate Limiting**: Tracks daily API usage (10,000/day limit) with configurable polling intervals

### API Integration

- **Base URL**: `https://openapi.api.govee.com/router/api/v1/`
- **Authentication**: API key header (`Govee-API-Key`)
- **Key Endpoints**:
  - `user/devices` - Get device list
  - `device/control` - Send commands
  - `device/state` - Get device state

## Development Tasks

### Testing API Responses
To test API changes or add new device support:
```bash
# Get device list
curl -H 'Govee-API-Key: YOUR_KEY' -o 'devices.json' -X GET https://openapi.api.govee.com/router/api/v1/user/devices

# Get device state
curl -H 'Govee-API-Key: YOUR_KEY' -X POST https://openapi.api.govee.com/router/api/v1/device/state \
  -H "Content-Type: application/json" \
  -d '{"sku":"MODEL_HERE","device":"MAC_HERE"}'
```

### Local Development
1. Copy `custom_components/goveelife` to your Home Assistant's `custom_components` folder
2. For testing without API calls, create a `_diagnostics.json` file with mock data
3. Restart Home Assistant and configure via UI

### Adding New Device Support
1. Check device capabilities in API response
2. Map device type to appropriate Home Assistant platform
3. Add capability handling in the corresponding platform file
4. Update entity attributes and services as needed

## Important Considerations

- **No Build System**: This is a standard Home Assistant custom component - no build/compile steps needed
- **HACS Compatible**: Follows HACS structure for easy distribution
- **API Rate Limits**: Be mindful of the 10,000 daily API call limit when testing
- **Cloud-Only**: No local control - all communication goes through Govee's cloud API