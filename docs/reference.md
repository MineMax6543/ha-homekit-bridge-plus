# HomeKit Bridge Plus reference

Everything that doesn't fit on the front page. Back to the [README](../README.md).

- [Compared to the built-in HomeKit Bridge](#compared-to-the-built-in-homekit-bridge)
- [Configure menu](#configure-menu)
- [Domains and HomeKit types](#domains-and-homekit-types)
- [TVs and receivers](#tvs-and-receivers)
- [Cameras](#cameras)
- [Accessory mode](#accessory-mode)
- [Actions](#actions)
- [Limits](#limits)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Compared to the built-in HomeKit Bridge

| | Built-in HomeKit Bridge | HomeKit Bridge Plus |
|---|---|---|
| Choosing entities | include/exclude filters | explicit list **+** labels, areas, domains, excludes; updates by itself when you re-label |
| Accessory type | limited, YAML | any sensible type in the UI (switch → light, outlet, fan, valve, sprinkler, motion or contact sensor …) |
| Exposed features | everything | per entity: light without color, fan without oscillation, blind without tilt, cover as open/close only |
| Thermostat and alarm modes | all / YAML | choose which modes Apple Home offers |
| Linked sensors | YAML | battery (with low threshold), humidity, motion, doorbell in the UI |
| Several entities in one tile | – | combined accessories |
| TV inputs | all | pick which inputs appear |
| Cameras | YAML | encoder, resolution, frame rate and audio in the UI |

## Configure menu

**Settings → Devices & services → HomeKit Bridge Plus → Configure.** Every change applies as
soon as you submit it: the bridge reloads and the Home app picks it up on its own.

| Menu | What it does |
|---|---|
| Choose entities | The explicit list of exposed entities. Entities that are exposed through a label, area, domain or combined accessory are listed there too, since removing them from this list has no effect. |
| Include by label / area / domain | Automatic includes. Hidden, disabled, config and diagnostic entities are skipped. **Exclude** always wins. |
| Configure an entity | Name, accessory type, exposed features, linked sensors. Only features the entity supports are offered. |
| Combined accessories | Several entities in one HomeKit accessory, e.g. a multi sensor or a fan with its light. The first entity decides the icon. |
| Bridge settings | Name, port, advertised IP. Shows the pairing PIN. |

Sensors whose type can't be guessed (no `device_class`) are skipped until you pick a type under
*Configure an entity*. The menu lists everything that was skipped and why.

## Domains and HomeKit types

| Domain | Types |
|---|---|
| light | Light bulb (brightness / color temp / color selectable), Switch, Outlet, Fan |
| switch, input_boolean | Switch, Outlet, Light bulb, Fan, Valve, Sprinkler, Shower, Faucet, Motion / Occupancy / Contact / Leak / Smoke / CO sensor |
| fan | Fan (speed / oscillation / direction selectable), Switch, Outlet, Light bulb |
| cover | Window covering (position / tilt selectable), Garage door, Door, Window, Switch |
| valve | Valve, Sprinkler, Shower, Faucet, Switch |
| lock | Lock, Switch |
| climate | Thermostat (modes, humidity, heat/cool range selectable), Switch |
| alarm_control_panel | Security system (arm modes selectable, code) |
| sensor | Temperature, Humidity, Light (lux), CO2, PM2.5, PM10, AQI |
| binary_sensor | Motion, Occupancy, Contact, Leak, Smoke, Carbon monoxide |
| person, device_tracker | Occupancy / Motion / Contact (home = detected) |
| media_player | Television / Receiver (accessory mode), Switch, Outlet |
| camera | Camera (live view, snapshots, audio, linked motion sensor and doorbell) |
| humidifier | Humidifier / dehumidifier (target humidity selectable), Switch, Fan |
| water_heater | Water heater (Heat, optional Off), Switch |
| vacuum, siren, remote, automation | Switch (vacuum also as Fan) |
| script, scene, button, input_button | Switch / Outlet / Light bulb that resets itself after a press |

## TVs and receivers

TVs only work in **accessory mode**; Apple doesn't show bridged TVs reliably. Choose which
inputs appear and which controls (power, inputs, volume, mute, play/pause). Play/pause and
next/previous control the media player. The other remote keys fire
`homekit_plus_tv_remote_key_pressed` with `entity_id` and `key_name`:

`arrow_up`, `arrow_down`, `arrow_left`, `arrow_right`, `select`, `back`, `exit`,
`information`, `rewind`, `fast_forward`

## Cameras

Cameras stream with the ffmpeg Home Assistant already ships. Per camera:

| Option | |
|---|---|
| Stream URL override | if the camera entity has no stream source |
| Video encoder | `libx264`; `copy` saves CPU for H.264 sources; `h264_v4l2m2m` / `h264_omx` for Raspberry Pi; `h264_qsv` for Intel |
| Audio | on/off |
| Max. width / height / frame rate | limits what iOS can ask for |
| Motion sensor | a binary sensor shown on the camera |
| Doorbell | a binary sensor or event entity; the camera then shows up as a video doorbell |

Bridged cameras work; accessory mode gives the most reliable live view. HomeKit Secure Video
recording is not supported.

## Accessory mode

One entity is paired directly, without a bridge. The options then only show *Choose entity*,
*Configure the entity* and *Bridge settings*. Changing the entity means pairing it again.

## Actions

| Action | |
|---|---|
| `homekit_plus.unpair` | Removes all pairings of a bridge (`config_entry_id`) so you can add it to Apple Home again |

## Limits

- A bridge holds max. **150 accessories**. Create a second bridge for more.
- Changing an entity's **type** makes Apple Home see a new accessory; its room and scenes are lost. Changing features is fine.
- Pairing data lives in `.storage/homekit_plus.<entry_id>.state`. Deleting the integration removes it.

## Troubleshooting

| Problem | Fix |
|---|---|
| Accessories show "No Response" | Check that the bridge port (default **21070**) is reachable from your Apple TV / HomePod. With several network interfaces or Docker, set the **Advertised IP** in *Bridge settings*. |
| An entity doesn't appear | Open *Configure*: the menu lists skipped entities and why. Sensors without a `device_class` need a type under *Configure an entity*. |
| Removed entity is still in Apple Home | It's included by a label, area or domain. Add it to **Exclude**. |
| "Port already in use" during setup | Another bridge (e.g. the built-in one) uses it. Pick a different port. |
| WLED tile only goes dark, not off | A segment light is exposed. Turn off *Keep main light* in the WLED integration, or expose the main light. |

## Development

```sh
pip install pytest-homeassistant-custom-component HAP-python PyQRCode base36 ha-ffmpeg
pytest
```

The tests run the integration inside a real Home Assistant instance and talk to it through the
HomeKit protocol layer.
