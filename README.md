<img src="custom_components/homekit_plus/brand/icon.png" alt="HomeKit Bridge Plus icon" width="96" align="right">

# HomeKit Bridge Plus

A Home Assistant custom integration that exposes entities to Apple HomeKit, like the
built-in **HomeKit Bridge**, but lets you pick exactly what is exposed and how, all
from the UI.

## What it adds compared to the built-in HomeKit Bridge

| | Built-in | Plus |
|---|---|---|
| Choose entities | include/exclude filters | explicit list **+** labels, areas, domains, excludes |
| Auto-update when you label/move entities | – | ✅ bridge reloads by itself |
| Accessory type per entity | limited (`type:` for switches in YAML) | any sensible type, in the UI (e.g. switch → light / outlet / fan / valve / sprinkler / **motion or contact sensor**) |
| Choose which characteristics are exposed | – | ✅ e.g. light without color, fan without oscillation, blind without tilt, cover as open/close only |
| Thermostat modes shown in HomeKit | all supported | ✅ choose (e.g. only Off/Heat) |
| Alarm arm modes shown | YAML | ✅ UI |
| Custom HomeKit name | YAML | ✅ UI |
| Linked battery / humidity sensor | YAML | ✅ UI, plus low battery threshold |
| Several entities in **one** accessory | – | ✅ "Combined accessories" |
| Invert binary sensors | – | ✅ |
| CO2 "detected" threshold | fixed | ✅ |
| TV inputs shown in HomeKit | all | ✅ pick which |
| Camera encoder / resolution / audio | YAML | ✅ UI |

## Installation

**Home Assistant Marketplace (2026.11 and newer)**

1. **Settings → Marketplace**, then **Add from link** (top right).
2. GitHub link: `MineMax6543/HomeKit-Bridge-Plus` → **Add**.
3. Open **HomeKit Bridge Plus** in the list and install it. The Marketplace continues straight
   into the setup below, no restart needed for the first install.

Updates show up in Home Assistant as an update entity, like any other update.

**Older Home Assistant (2026.10 and earlier)**: add the same repository in HACS under
⋮ → **Custom repositories** (type *Integration*), download it and restart.

**Manual**: copy `custom_components/homekit_plus` into `config/custom_components/` and restart.

**Setup**

1. **Settings → Devices & services → Add integration → HomeKit Bridge Plus**.
   Choose **Bridge** (many entities, paired once) or **Accessory** (one entity paired on
   its own; required for TVs/receivers, recommended for cameras).
2. A notification with a QR code and pairing PIN appears. Scan it in the Apple Home app
   (*Add Accessory*).

You can run this alongside the built-in HomeKit Bridge, but use a different port
(default here is `21070`) and don't expose the same entity through both.

## Configuring

Open the integration's **Configure** button and pick what to change. Each change is applied
as soon as you submit it: the bridge reloads and the Home app picks it up on its own.

* **Choose entities**: an explicit list.
* **Include by label / area / domain**: e.g. create a label `HomeKit` and put it on any
  entity or device. Hidden, disabled, config and diagnostic entities are skipped for these
  automatic includes. **Exclude** always wins.
* **Configure an entity**: name, accessory type, then which features are exposed and
  linked battery/humidity sensors. Only features the entity actually supports are offered.
* **Combined accessories**: put several entities in one HomeKit accessory (for example a
  temperature + humidity + motion multi sensor, or a fan + its light).
* **Bridge settings**: name, port, advertised IP.

Sensors whose type can't be guessed (no `device_class`) are skipped until you pick a type
under *Configure an entity*. The options menu lists what was skipped and why.

### Supported domains → HomeKit types

| Domain | Types |
|---|---|
| light | Light bulb (brightness / color temp / color selectable), Switch, Outlet, Fan |
| switch, input_boolean | Switch, Outlet, Light bulb, Fan, Valve, Sprinkler, Shower, Faucet, Motion/Occupancy/Contact/Leak/Smoke/CO sensor |
| fan | Fan (speed / oscillation / direction selectable), Switch, Outlet, Light bulb |
| cover | Window covering (position / tilt selectable), Garage door, Door, Window, Switch |
| valve | Valve, Sprinkler, Shower, Faucet, Switch |
| lock | Lock, Switch |
| climate | Thermostat (modes, humidity, heat/cool range selectable), Switch |
| alarm_control_panel | Security system (arm modes selectable, code) |
| sensor | Temperature, Humidity, Light (lux), CO2, PM2.5, PM10, AQI |
| binary_sensor | Motion, Occupancy, Contact, Leak, Smoke, Carbon monoxide |
| person, device_tracker | Occupancy / Motion / Contact (home = detected) |
| media_player | Television / Receiver (accessory mode: power, inputs, volume, mute, play/pause, remote keys selectable), Switch, Outlet |
| camera | Camera (live stream via ffmpeg, snapshots, audio, linked motion sensor and doorbell) |
| humidifier | Humidifier / dehumidifier (target humidity selectable, linked humidity sensor), Switch, Fan |
| water_heater | Water heater (thermostat with Heat / optional Off), Switch |
| vacuum, siren, remote, automation | Switch (vacuum also as Fan) |
| script, scene, button, input_button | Switch / Outlet / Light bulb that resets itself after a press |

### TVs

TVs and receivers only work in **accessory mode** (one entity per pairing, Apple doesn't
show bridged TVs reliably). Pick which inputs appear in HomeKit. Play/pause and
next/previous call the media player; the other remote keys (arrows, select, back, info…)
fire the event `homekit_plus_tv_remote_key_pressed` with `entity_id` and `key_name`
(`arrow_up`, `arrow_down`, `arrow_left`, `arrow_right`, `select`, `back`, `exit`,
`information`, `rewind`, `fast_forward`) so you can map them in an automation.

### Cameras

Cameras stream with the ffmpeg binary Home Assistant already uses. Per camera you can set:
a stream URL override (if the camera entity has no stream source), the encoder (`copy` avoids
re-encoding and saves CPU if the source is H.264; `h264_v4l2m2m`/`h264_omx` for Raspberry Pi,
`h264_qsv` for Intel), audio on/off, max resolution and frame rate, a motion sensor and a
doorbell (binary sensor or event entity; the accessory then shows up as a video doorbell).
Cameras work bridged, but accessory mode gives the most reliable live view.
HomeKit Secure Video recording is not supported.

## Accessory mode

One entity is paired directly (no bridge). The options menu then only shows *Choose entity*,
*Configure the entity* and *Bridge settings*. Changing the entity in accessory mode means
re-pairing in the Home app.

## Services

* `homekit_plus.unpair`: removes all pairings of a bridge so you can add it again.

## Notes

* A HomeKit bridge holds max. 150 accessories. Create a second bridge for more.
* Changing an entity's **type** after pairing makes the Home app treat it as a new
  accessory (room/scene assignments for that accessory are lost). Changing features is fine.
* Pairing data lives in `.storage/homekit_plus.<entry_id>.state`. Deleting the integration
  removes it.

## Disclaimer

Not affiliated with or endorsed by Apple or Home Assistant. HomeKit and Apple Home are
trademarks of Apple Inc. Like everything in the Marketplace, this is community code that
Home Assistant does not test or audit.
