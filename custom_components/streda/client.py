# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Own MQTT connection to the Streda box, independent of Home Assistant's MQTT integration.

Home Assistant can only be connected to one MQTT broker. Using a separate connection means the Streda box
works next to any MQTT setup a user already has.

paho-mqtt runs its network loop in a background thread; every callback is handed over to Home Assistant's
event loop, so the rest of the integration only runs on the event loop.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import threading
from typing import Any
from uuid import uuid4

import paho.mqtt.client as paho

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

KEEPALIVE = 60
PROBE_TIMEOUT = 10
# MQTT 3.1.1 return codes 4/5 and MQTT 5 reason codes 134/135: bad credentials / not authorised.
AUTH_FAILURES = {4, 5, 134, 135}


def _new_client(username: str | None, password: str | None, purpose: str) -> paho.Client:
    client = paho.Client(
        paho.CallbackAPIVersion.VERSION2,
        client_id=f"ha-streda-{purpose}-{uuid4().hex[:8]}",
        protocol=paho.MQTTv311,
    )
    if username:
        client.username_pw_set(username, password or None)
    return client


def probe(host: str, port: int, username: str | None, password: str | None, base: str) -> tuple[int | None, str | None]:
    """Connect once and read the retained device list (blocking; run in an executor).

    Returns (number of devices, None) on success, or (None, error key) on failure.
    """
    done = threading.Event()
    result: dict[str, Any] = {}
    client = _new_client(username, password, "setup")

    def on_connect(c: paho.Client, userdata: Any, flags: Any, reason: Any, props: Any) -> None:
        if reason.is_failure:
            result["error"] = "invalid_auth" if reason.value in AUTH_FAILURES else "cannot_connect"
            done.set()
        else:
            c.subscribe(f"{base}/bridge/devices")

    def on_message(c: paho.Client, userdata: Any, msg: paho.MQTTMessage) -> None:
        try:
            devices = json.loads(msg.payload)
            result["count"] = sum(1 for d in devices if d.get("type") != "Coordinator")
        except (TypeError, ValueError, AttributeError):
            result["count"] = 0
        done.set()

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(host, port, keepalive=30)
    except (OSError, ValueError) as err:
        _LOGGER.debug("Cannot connect to %s:%s: %s", host, port, err)
        return None, "cannot_connect"
    client.loop_start()
    try:
        done.wait(PROBE_TIMEOUT)
    finally:
        client.disconnect()
        client.loop_stop()
    if "error" in result:
        return None, result["error"]
    if "count" not in result:
        return None, "no_device_list"
    return result["count"], None


class StredaClient:
    """Long-running connection to the Streda box with automatic reconnect."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        subscriptions: list[str],
        on_message: Callable[[str, bytes], None],
        on_connection: Callable[[bool], None],
    ) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._subscriptions = subscriptions
        self._on_message = on_message
        self._on_connection = on_connection
        self._client = _new_client(username, password, "hub")
        self._client.reconnect_delay_set(min_delay=1, max_delay=60)
        self._client.on_connect = self._paho_connect
        self._client.on_disconnect = self._paho_disconnect
        self._client.on_message = self._paho_message

    def start(self) -> None:
        """Start connecting in the background (blocking parts only; run in an executor)."""
        self._client.connect_async(self._host, self._port, keepalive=KEEPALIVE)
        self._client.loop_start()

    def stop(self) -> None:
        """Disconnect and stop the network thread (blocking; run in an executor)."""
        self._client.disconnect()
        self._client.loop_stop()

    def publish(self, topic: str, payload: str) -> None:
        """Publish a device command. Never retained."""
        self._client.publish(topic, payload, qos=0, retain=False)

    # paho callbacks run in paho's network thread: hand everything over to the event loop.

    def _paho_connect(self, client: paho.Client, userdata: Any, flags: Any, reason: Any, props: Any) -> None:
        if reason.is_failure:
            _LOGGER.warning("Streda box %s:%s refused the connection: %s", self._host, self._port, reason)
            return
        _LOGGER.debug("Connected to Streda box %s:%s", self._host, self._port)
        client.subscribe([(topic, 0) for topic in self._subscriptions])
        self._hass.loop.call_soon_threadsafe(self._on_connection, True)

    def _paho_disconnect(self, client: paho.Client, userdata: Any, flags: Any, reason: Any, props: Any) -> None:
        _LOGGER.debug("Disconnected from Streda box %s:%s: %s", self._host, self._port, reason)
        self._hass.loop.call_soon_threadsafe(self._on_connection, False)

    def _paho_message(self, client: paho.Client, userdata: Any, msg: paho.MQTTMessage) -> None:
        self._hass.loop.call_soon_threadsafe(self._on_message, msg.topic, msg.payload)
