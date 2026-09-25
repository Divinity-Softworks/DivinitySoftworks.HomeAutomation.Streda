# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""The Isolectra Streda integration.

Makes the devices of an Isolectra Streda installation (Zigbee2MQTT on the Streda box) available in
Home Assistant, over its own connection to the box's MQTT broker.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, DEFAULT_PORT, PLATFORMS
from .hub import StredaHub

_LOGGER = logging.getLogger(__name__)

type StredaConfigEntry = ConfigEntry[StredaHub]


async def async_setup_entry(hass: HomeAssistant, entry: StredaConfigEntry) -> bool:
    data = entry.data
    hub = StredaHub(
        hass,
        entry.entry_id,
        data[CONF_HOST],
        data.get(CONF_PORT, DEFAULT_PORT),
        data.get(CONF_USERNAME),
        data.get(CONF_PASSWORD),
        data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC),
    )
    if not await hub.async_start():
        raise ConfigEntryNotReady(f"No device list received from the Streda box at {data[CONF_HOST]}")

    @callback
    def _reload_for_new_devices() -> None:
        hass.config_entries.async_schedule_reload(entry.entry_id)

    hub.on_new_devices = _reload_for_new_devices
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StredaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 (0.1.x) used Home Assistant's MQTT connection; take the box's address from it."""
    if entry.version == 1:
        mqtt_entries = hass.config_entries.async_entries("mqtt")
        if not mqtt_entries or not mqtt_entries[0].data.get("broker"):
            _LOGGER.error(
                "Cannot migrate the Streda entry: no MQTT broker address found. "
                "Remove the Streda integration and add it again with the Streda box's IP address"
            )
            return False
        mqtt = mqtt_entries[0].data
        new_data = {
            CONF_HOST: mqtt["broker"],
            CONF_PORT: mqtt.get("port", DEFAULT_PORT),
            CONF_BASE_TOPIC: entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC),
        }
        if mqtt.get("username"):
            new_data[CONF_USERNAME] = mqtt["username"]
            new_data[CONF_PASSWORD] = mqtt.get("password")
        hass.config_entries.async_update_entry(
            entry, data=new_data, unique_id=f"{new_data[CONF_HOST]}:{new_data[CONF_PORT]}", version=2
        )
        _LOGGER.info("Migrated the Streda entry to its own connection to %s", new_data[CONF_HOST])
    return True
