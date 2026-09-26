# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Find Streda boxes on the local network, read-only.

Two passes: a quick TCP check for the MQTT port on every address of Home Assistant's own networks, then,
for each address that answers, one read of the retained device list. Only a broker whose device list
contains Streda devices counts as a Streda box, so another MQTT broker on the network is never offered.
Nothing is published and nothing is changed on any device.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, ip_interface
import logging

from homeassistant.components import network
from homeassistant.core import HomeAssistant

from .client import count_devices, read_device_list
from .const import DEFAULT_BASE_TOPIC, DEFAULT_PORT, STREDA_ZIGBEE_MANUFACTURER

_LOGGER = logging.getLogger(__name__)

# Scan at most 1024 addresses per network. Mesh routers such as TP-Link Deco hand out a /22
# (192.168.68.0 - 192.168.71.255); bigger networks are narrowed to the /22 around Home Assistant.
MAX_PREFIX = 22
CONNECT_TIMEOUT = 1.0
CONCURRENCY = 128
CONFIRM_TIMEOUT = 5


@dataclass(frozen=True)
class FoundBox:
    """A Streda box that answered on the network."""

    host: str
    port: int
    devices: int


async def async_networks(hass: HomeAssistant) -> list[IPv4Network]:
    """The private IPv4 networks of Home Assistant's enabled network adapters."""
    networks: set[IPv4Network] = set()
    for adapter in await network.async_get_adapters(hass):
        if not adapter["enabled"]:
            continue
        for ip in adapter["ipv4"]:
            iface = ip_interface(f"{ip['address']}/{ip['network_prefix']}")
            if not iface.ip.is_private or iface.ip.is_loopback or iface.ip.is_link_local:
                continue
            net = iface.network
            if net.prefixlen < MAX_PREFIX:
                net = ip_interface(f"{iface.ip}/{MAX_PREFIX}").network
            networks.add(net)
    return sorted(networks)


async def _port_open(host: str, port: int, limit: asyncio.Semaphore) -> bool:
    async with limit:
        try:
            _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
        except (OSError, TimeoutError):
            return False
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
        return True


def streda_device_count(host: str, port: int, base: str) -> int:
    """Number of devices if the broker at host:port is a Streda box, else 0 (blocking; run in an executor)."""
    devices, _error = read_device_list(host, port, None, None, base, CONFIRM_TIMEOUT)
    if not devices or not any(d.get("manufacturer") == STREDA_ZIGBEE_MANUFACTURER for d in devices):
        return 0
    return count_devices(devices)


async def async_find_boxes(
    hass: HomeAssistant, port: int = DEFAULT_PORT, base: str = DEFAULT_BASE_TOPIC
) -> list[FoundBox]:
    """Scan Home Assistant's own networks for Streda boxes that don't require a login."""
    hosts = [str(host) for net in await async_networks(hass) for host in net.hosts()]
    _LOGGER.debug("Looking for Streda boxes on port %s of %s addresses", port, len(hosts))

    limit = asyncio.Semaphore(CONCURRENCY)
    answers = await asyncio.gather(*(_port_open(host, port, limit) for host in hosts))
    candidates = [host for host, is_open in zip(hosts, answers, strict=True) if is_open]
    _LOGGER.debug("Port %s is open on %s", port, candidates)

    counts = await asyncio.gather(
        *(hass.async_add_executor_job(streda_device_count, host, port, base) for host in candidates)
    )
    boxes = [FoundBox(host, port, count) for host, count in zip(candidates, counts, strict=True) if count]
    _LOGGER.debug("Streda boxes found: %s", boxes)
    return sorted(boxes, key=lambda box: IPv4Address(box.host))
