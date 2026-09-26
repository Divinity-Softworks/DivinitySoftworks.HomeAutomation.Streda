# Isolectra Streda for Home Assistant

Custom integration that makes the devices of an **Isolectra Streda** installation available in Home Assistant:
lights, relays, dimmers, wall switches, the doorbell and smoke detectors.

The Streda box runs **Zigbee2MQTT** with an MQTT broker on your home network, but has Home Assistant discovery
turned off. This integration reads the box's device list and creates the entities itself, so all devices appear
without any manual configuration.

> **Unofficial.** This project is not affiliated with or supported by Isolectra. A firmware update of the Streda
> box may change its behaviour.

## Read-only towards the Streda box

The box is the heart of the house's electrical installation, so the integration never changes it:

- it only **subscribes** to the box's MQTT topics;
- the only messages it publishes are **device commands** (`zigbee2mqtt/<device>/set`), and only when you or an
  automation switch an entity;
- it never sends Zigbee2MQTT bridge requests, never publishes retained messages and never changes settings.

## What you get

| Streda device | Entities |
|---|---|
| Relays (e.g. ceiling light points `BN1-C`, wired wall units `SN3`) | Switch per relay channel, current (A) and estimated power (W) |
| Dimmer (`SN2-E`) | Dimmable light |
| Wall switches (battery `BN0-S` / `BN0-T`, wired `SN3`) | Button event per press (`singleup`, `singledown`, `doubledown`, ... with `channel` attribute), battery level and battery-low |
| Front door unit (`SN3-1TB5K`) | Doorbell event (`ring`) |
| Smoke detectors (Develco `SMSZB-120`) | Smoke, fault, battery-low, battery level, temperature |
| All devices | Link quality (diagnostic, disabled by default) |

Behaviour worth knowing:

- **Relays are switches.** For a relay that drives a lamp, use *Show as → Light* in the entity settings.
- **Relays on wired wall units follow their own button.** On `SN3` units the relay switches locally when its
  button is pressed without reporting it; the relay entity follows the button presses so its state stays right.
- **Battery levels are remembered across restarts**, because battery devices only report now and then
  (mostly when pressed).
- The box does **not keep device states** on the broker: an entity shows *unknown* until the device reports or
  is switched. The box polls devices regularly, so states fill in by themselves.
- Which wall button controls which light is configured inside the Streda box and is not visible over MQTT.
  Remote-controlled changes that a device does not report (for example switching a dimmer off with a
  double-click on another unit) need a small automation.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add this repository's URL, type **Integration**.
2. Install **Isolectra Streda** and restart Home Assistant.

### Manual

Copy `custom_components/streda` to `/config/custom_components/streda` and restart Home Assistant.

## Setup

1. **Add the Isolectra Streda integration** (Settings → Devices & services → Add integration). It first
   searches your network for Streda boxes (up to half a minute) and lists the ones it finds: pick yours.
2. **Not found?** Choose *Enter the IP address myself* (or you get that form directly) and enter the box's
   IP address, port `1883`, no username/password (unless your box has one), base topic `zigbee2mqtt`.
   See [Finding the IP address of the box](#finding-the-ip-address-of-the-box).
3. All devices appear with generic names such as *Streda BN1-C c75a*. Name them and assign rooms in the UI.
   Tip: press a wall switch and watch which relay changes in the logbook to find out which is which.

Preferably reserve a fixed IP address for the box in your router (DHCP reservation), so it does not change.

### How the search works

The search is read-only, like the rest of the integration. It checks every address of Home Assistant's own
network (at most 1024 addresses, e.g. a /22) for an open MQTT port `1883`. Each address that answers is asked
once for its device list (`zigbee2mqtt/bridge/devices`); only a broker whose list contains Streda devices
(manufacturer `TKHTechnology`) is offered. Nothing is published. The search does not find a box that requires a
login, that is on another network (VLAN) than Home Assistant, or when Home Assistant runs in Docker without
host networking; enter the address yourself in those cases.

### Finding the IP address of the box

- **Router:** look in your router's (or mesh app's) list of connected devices. The box has no name there;
  look for a MAC address starting with `00:E6:E8`.
- **Port scan** from a computer on the same network (adjust the range to yours, see `ipconfig` / `ip addr`):

  ```bash
  nmap -p 1883,8888 --open 192.168.68.0/22
  ```

  The box answers on port `1883` (MQTT) and `8888` (its Zigbee2MQTT dashboard: look, don't change).
- **Confirm** it is the box (read-only):

  ```bash
  docker run --rm eclipse-mosquitto mosquitto_sub -h <ip> -p 1883 -t "zigbee2mqtt/bridge/info" -C 1
  ```

The integration uses **its own connection** to the box. You do not need Home Assistant's MQTT integration,
and an existing MQTT setup (for example your own Mosquitto broker) is not affected.
If the box gets a new IP address: Settings → Devices & services → Isolectra Streda → ⋮ → **Reconfigure**.

### Upgrading from 0.1.x

Version 0.1.x used Home Assistant's MQTT integration. On upgrade, the Streda entry takes the box's address
from that MQTT connection automatically; entities and names stay the same. If the MQTT integration was only
used for the Streda box, you can remove it afterwards.

## Languages

English and Dutch.

## Requirements

- Home Assistant 2025.1 or newer
- Network access from Home Assistant to the Streda box (same home network)
- `paho-mqtt` (included with Home Assistant)

## Development

Tested against a Streda box running Zigbee2MQTT 2.6 with the models listed above. Model-specific knowledge
(which relay follows which button, the doorbell input) lives in `custom_components/streda/const.py`.

## License

MIT, see [LICENSE](LICENSE).
