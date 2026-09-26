# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Connection to the Streda box (Zigbee2MQTT) and the state of its devices.

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

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import StredaClient
from .const import signal_device

_LOGGER = logging.getLogger(__name__)

DEVICE_LIST_TIMEOUT = 20


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

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        base_topic: str,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.base = base_topic
        self.devices: dict[str, StredaDevice] = {}
        self.connected = False
        self._stopping = False
        self._by_name: dict[str, str] = {}
        self._device_list = asyncio.Event()
        self.on_new_devices: Any = None
        self._client = StredaClient(
            hass,
            host,
            port,
            username,
            password,
            subscriptions=[f"{base_topic}/bridge/devices", f"{base_topic}/+", f"{base_topic}/+/availability"],
            on_message=self._on_message,
            on_connection=self._on_connection,
        )

    async def async_start(self) -> bool:
        """Connect and wait for the retained device list. Returns False when none arrives."""
        await self.hass.async_add_executor_job(self._client.start)
        try:
            await asyncio.wait_for(self._device_list.wait(), DEVICE_LIST_TIMEOUT)
        except TimeoutError:
            await self.async_stop()
            return False
        return True

    async def async_stop(self) -> None:
        self._stopping = True
        await self.hass.async_add_executor_job(self._client.stop)

    @callback
    def _on_connection(self, connected: bool) -> None:
        if connected == self.connected:
            return
        self.connected = connected
        if not connected and not self._stopping:
            _LOGGER.warning("Lost the connection to the Streda box; reconnecting")
        for ieee in self.devices:
            async_dispatcher_send(self.hass, signal_device(self.entry_id, ieee), None)

    @callback
    def _on_message(self, topic: str, payload: bytes) -> None:
        if topic == f"{self.base}/bridge/devices":
            self._on_device_list(payload)
        elif topic.endswith("/availability"):
            self._on_availability(topic[len(self.base) + 1 : -len("/availability")], payload)
        else:
            self._on_state(topic[len(self.base) + 1 :], payload)

    @callback
    def _on_device_list(self, payload: bytes) -> None:
        try:
            raw = json.loads(payload)
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid device list received from the Streda box")
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
    def _on_state(self, name: str, payload: bytes) -> None:
        ieee = self._by_name.get(name)
        if ieee is None:
            return
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.devices[ieee].state.update(data)
        async_dispatcher_send(self.hass, signal_device(self.entry_id, ieee), data)

    @callback
    def _on_availability(self, name: str, payload: bytes) -> None:
        ieee = self._by_name.get(name)
        if ieee is None:
            return
        try:
            state = json.loads(payload).get("state")
        except (TypeError, ValueError, AttributeError):
            state = payload.decode(errors="ignore")
        device = self.devices[ieee]
        available = state == "online"
        if available != device.available:
            device.available = available
            async_dispatcher_send(self.hass, signal_device(self.entry_id, ieee), None)

    async def async_command(self, device: StredaDevice, payload: dict[str, Any]) -> None:
        """Send a device command (never retained)."""
        await self.hass.async_add_executor_job(
            self._client.publish, f"{self.base}/{device.friendly_name}/set", json.dumps(payload)
        )
