"""The Isolectra Streda integration.

Makes the devices of an Isolectra Streda installation (Zigbee2MQTT on the Streda box) available in
Home Assistant. Requires the MQTT integration to be connected to the Streda box.
"""

from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, PLATFORMS
from .hub import StredaHub

type StredaConfigEntry = ConfigEntry[StredaHub]


async def async_setup_entry(hass: HomeAssistant, entry: StredaConfigEntry) -> bool:
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT is not connected")

    hub = StredaHub(hass, entry.entry_id, entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC))
    if not await hub.async_start():
        raise ConfigEntryNotReady("No device list received from the Streda box")

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
        entry.runtime_data.async_stop()
    return unloaded
