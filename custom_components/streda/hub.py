"""Connection to the Streda box (Zigbee2MQTT) through Home Assistant's MQTT integration.

Read-only towards the box: the hub only subscribes. The only messages ever published are device
commands (`<base>/<device>/set`) when a user or automation switches an entity. It never sends bridge
requests, never publishes retained messages and never changes the box's configuration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import signal_device

_LOGGER = logging.getLogger(__name__)

DEVICE_LIST_TIMEOUT = 15


@dataclass
class StredaDevice:
    """A device from Zigbee2MQTT's device list."""

    ieee: str
    friendly_name: str
    model: str
    vendor: str | None
    manufacturer: str | None
    description: str | None
    software: str | None
    power_source: str | None
    type: str
    exposes: list[dict[str, Any]]
    state: dict[str, Any] = field(default_factory=dict)
    available: bool = True

    @property
    def battery_powered(self) -> bool:
        return self.type == "EndDevice"


class StredaHub:
    """Keeps the device list and the latest state per device, and dispatches updates to entities."""

    def __init__(self, hass: HomeAssistant, entry_id: str, base_topic: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.base = base_topic
        self.devices: dict[str, StredaDevice] = {}
        self._by_name: dict[str, str] = {}
        self._unsubs: list[CALLBACK_TYPE] = []
        self._device_list = asyncio.Event()
        self.on_new_devices: CALLBACK_TYPE | None = None

    async def async_start(self) -> bool:
        """Subscribe and wait for the retained device list. Returns False when none arrives."""
        self._unsubs.append(
            await mqtt.async_subscribe(self.hass, f"{self.base}/bridge/devices", self._on_device_list)
        )
        try:
            await asyncio.wait_for(self._device_list.wait(), DEVICE_LIST_TIMEOUT)
        except TimeoutError:
            self.async_stop()
            return False
        self._unsubs.append(await mqtt.async_subscribe(self.hass, f"{self.base}/+", self._on_state))
        self._unsubs.append(
            await mqtt.async_subscribe(self.hass, f"{self.base}/+/availability", self._on_availability)
        )
        return True

    @callback
    def async_stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def _on_device_list(self, msg: mqtt.ReceiveMessage) -> None:
        try:
            raw = json.loads(msg.payload)
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid device list on %s", msg.topic)
            return
        devices: dict[str, StredaDevice] = {}
        for d in raw:
            definition = d.get("definition")
            if d.get("type") == "Coordinator" or not definition or d.get("disabled"):
                continue
            ieee = d["ieee_address"]
            devices[ieee] = self.devices.get(ieee) or StredaDevice(
                ieee=ieee,
                friendly_name=d["friendly_name"],
                model=definition.get("model") or d.get("model_id") or "unknown",
                vendor=definition.get("vendor"),
                manufacturer=d.get("manufacturer"),
                description=definition.get("description"),
                software=d.get("software_build_id"),
                power_source=d.get("power_source"),
                type=d.get("type", ""),
                exposes=definition.get("exposes", []),
            )
        new = set(devices) - set(self.devices)
        first = not self._device_list.is_set()
        self.devices = devices
        self._by_name = {dev.friendly_name: ieee for ieee, dev in devices.items()}
        self._device_list.set()
        if new and not first and self.on_new_devices:
            _LOGGER.info("New Streda devices found: %s", ", ".join(sorted(new)))
            self.on_new_devices()

    @callback
    def _on_state(self, msg: mqtt.ReceiveMessage) -> None:
        ieee = self._by_name.get(msg.topic[len(self.base) + 1 :])
        if ieee is None:
            return
        try:
            payload = json.loads(msg.payload)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        device = self.devices[ieee]
        device.state.update(payload)
        async_dispatcher_send(self.hass, signal_device(self.entry_id, ieee), payload)

    @callback
    def _on_availability(self, msg: mqtt.ReceiveMessage) -> None:
        name = msg.topic[len(self.base) + 1 : -len("/availability")]
        ieee = self._by_name.get(name)
        if ieee is None:
            return
        try:
            state = json.loads(msg.payload).get("state")
        except (TypeError, ValueError, AttributeError):
            state = msg.payload
        device = self.devices[ieee]
        available = state == "online"
        if available != device.available:
            device.available = available
            async_dispatcher_send(self.hass, signal_device(self.entry_id, ieee), None)

    async def async_command(self, device: StredaDevice, payload: dict[str, Any]) -> None:
        """Send a device command, exactly like the Streda app would (never retained)."""
        await mqtt.async_publish(
            self.hass, f"{self.base}/{device.friendly_name}/set", json.dumps(payload), qos=0, retain=False
        )
