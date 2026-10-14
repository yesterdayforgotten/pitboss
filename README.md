# Pit Boss for Home Assistant

Local control and cook tracking for Wi-Fi Pit Boss pellet smokers. Home Assistant talks to the smoker directly on your network; there's no cloud account and no Pit Boss app involved.

- Set the smoker temperature and probe targets, prime the auger, and turn the smoker off.
- Probe temperatures, rate of rise, **estimated done time**, stall and done detection.
- **Alerts** when a probe is done, a stall starts or ends, the fire goes out or the hopper runs dry, or the controller reports an error.
- A **cook archive** in the sidebar: every cook's temperature graph, with a live view while you cook, notes and details, side-by-side comparison, and CSV export.

## Installation

### HACS (recommended)

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/yesterdayforgotten/pitboss` as an **Integration**.
2. Install **Pitboss Integration** and restart Home Assistant.

Requires Home Assistant 2024.11 or newer.

### Manual

Copy this repository into `config/custom_components/pitboss/` and restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → Pitboss**, then either:

- **Discover on local network**: scans your local subnets for smokers. If Home Assistant runs in Docker or a VM and nothing is found, you can enter your LAN subnet (for example `192.168.1.0/24`) to scan instead.
- **Enter host manually**: type the smoker's IP address.

Give the smoker a fixed IP (a DHCP reservation in your router) so it doesn't move. If its address changes anyway, use **Reconfigure** on the integration to point it at the new one.

**Options:** polling interval (default 15 seconds, 5–300).

## Entities

| Entity | What it does |
| --- | --- |
| Grill Control (climate) | Smoker on/off and setpoint. The smoker moves in 10°F steps. |
| Probe 1 Target Temperature | Probe 1 target, stored on the smoker. |
| Probe 2 Target Temperature | Probe 2 target. **The controller has no probe 2 target, so this one is stored only in Home Assistant**; the smoker's own display won't show it. |
| Primer | Runs the auger to prime pellets. |
| Probe 1/2 Temperature | Unavailable when the probe is unplugged. |
| Probe 1/2 Estimated Done | When the probe should reach its target, based on the last 30 minutes of rise. Unknown during a stall, before there's 10 minutes of data, or if the estimate is over 24 hours. |
| Probe 1/2 Delta to Target | Degrees left to go. |
| Probe 1/2 Done | On once the probe has held its target for 5 minutes. |
| Probe 1/2 Stall | On when the probe has been flat (within 2° per hour) for 20 minutes above 140°F / 60°C. |
| Probe 1/2 Time Since Done | Minutes since the probe reached its target (handy for resting). |
| Smoker Temperature Alert | On when the smoker has been more than 25°F / 15°C from its setpoint for 10 minutes. Only armed after the smoker first reaches the setpoint, so warm-up and setpoint changes don't trip it. Usually means a flameout or an empty hopper. |
| Error Status / Error Information | Controller errors, in plain language (for example "Out of pellets"). |
| Cook Active, Current/Last Cook Duration, Last Cook Start/End | Cook tracking (see below). |
| Temperature rate sensors | Degrees per hour for the smoker and each probe. |
| Diagnostics | Firmware, Wi-Fi and memory sensors, disabled by default. |

## Alerts and automations

### Blueprint

The bundled blueprint sends companion-app notifications for whichever alerts you choose:

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fyesterdayforgotten%2Fpitboss%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fpitboss%2Fcook_alerts.yaml)

By default it notifies on probe done, smoker temperature alerts and recovery, and controller errors. Stall and cook start/finish notifications can be switched on.

### Events

Everything the blueprint uses is available to your own automations as a `pitboss_event` on the event bus. Every event carries `type`, `device_id`, `config_entry_id` and `unit` (`F` or `C`), plus:

| `type` | Extra data |
| --- | --- |
| `probe_done` | `probe` (1 or 2), `temperature`, `target` |
| `stall_started`, `stall_ended` | `probe`, `temperature` |
| `grill_temp_alert` | `temperature`, `target`, `direction` (`low` or `high`) |
| `grill_temp_recovered` | `temperature`, `target` |
| `error` | `codes` (for example `["NoPellets"]`), `message` |
| `cook_started` | `cook_id`, `start` |
| `cook_ended` | `cook_id`, `start`, `end`, `duration_minutes`, `title` |

`probe_done` fires once per target: it won't repeat while the probe hovers around the target during a rest, only after the target changes or the probe drops 5°F / 3°C below it. Stall start and end are announced once the change has held for 5 minutes. The first poll after Home Assistant starts only records the current state, so a restart doesn't re-announce errors or finished probes.

```yaml
triggers:
  - trigger: event
    event_type: pitboss_event
    event_data:
      type: probe_done
      probe: 1
```

## Cook archive

Each smoker gets a **Cooks** page in the sidebar (admins only).

- **When a cook is recorded:** a cook starts when probe 1 is plugged in. Once it has been in for an hour, the cook is kept; shorter sessions are discarded. The cook ends 30 minutes after probe 1 is unplugged, so a quick unplug to move the probe doesn't split it. Temperatures are sampled every 5 minutes.
- **Live view:** while a cook is running it appears at the top of the list with current temperatures, ETA, stall and done status, and any alerts, updating on every poll.
- **Details:** give each cook a title, food, weight, pellets or wood, tags and notes, during the cook or afterwards. Search covers all of them.
- **Compare:** overlay another cook's graph, lined up by time since the start, to see how this brisket is tracking against the last one.
- **CSV:** download a cook's temperature log.

Cook data lives in Home Assistant's `.storage` folder and is deleted when you remove the integration.

## Troubleshooting

- **Smoker not found by discovery:** make sure it's on the same network as Home Assistant and powered on, then try the custom subnet scan or enter the IP manually.
- **Entities unavailable:** Home Assistant can't reach the smoker (it's unplugged, off Wi-Fi, or its IP changed). Entities come back on the next successful poll; if the IP changed, use **Reconfigure**.
- **Bug reports:** [open an issue](https://github.com/yesterdayforgotten/pitboss/issues) and include debug logs (enable debug logging on the integration, reproduce the problem, then disable it to download the log).
