# Copyright (c) 2026 Michael K. @ Divinity Softworks
# SPDX-License-Identifier: MIT

"""Constants for the Isolectra Streda integration."""

from homeassistant.const import Platform

DOMAIN = "streda"

CONF_BASE_TOPIC = "base_topic"
DEFAULT_BASE_TOPIC = "zigbee2mqtt"
DEFAULT_PORT = 1883

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.LIGHT, Platform.SENSOR, Platform.SWITCH]

MANUFACTURER = "Isolectra Streda"
STREDA_ZIGBEE_MANUFACTURER = "TKHTechnology"

# Button actions as the box sends them, without the channel suffix: `singleup_l3` -> `singleup`.
EVENT_TYPES = [
    f"{press}{side}"
    for press in ("single", "double", "hold", "release", "long", "longpressed")
    for side in ("", "up", "down")
] + ["other"]

# Wired wall units with their own relays: the relay switches locally when its button is pressed and does
# not report that, so the relay entity follows the button's up/down presses (observed on both models).
FOLLOW_BUTTON = {
    "SN3-1TB5K-03/PW": {"l7": "l5"},
    "SN3-1TB5-03/PW": {"l7": "l5"},
}

# Doorbell push input (observed on the front door unit, SN3-1TB5K).
DOORBELL_INPUT = {"SN3-1TB5K-03/PW": "l8"}

# Mains voltage used to estimate power from the reported current.
MAINS_VOLTAGE = 230


def signal_device(entry_id: str, ieee: str) -> str:
    """Dispatcher signal for state updates of one device."""
    return f"{DOMAIN}_{entry_id}_{ieee}"
