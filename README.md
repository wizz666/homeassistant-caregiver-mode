# Caregiver Mode for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/wizz666/homeassistant-caregiver-mode/releases)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Stöd_projektet-F16061?logo=ko-fi&logoColor=white)](https://ko-fi.com/wizz666)

AI-assisted motion monitoring for elderly or vulnerable persons living independently. Caregiver Mode watches your motion sensors and sends contextual alerts — via the HA mobile app, Telegram, or Ntfy — if no activity is detected for a configurable number of hours.

## Features

- **Multi-channel notifications** — HA mobile app, Telegram Bot, and/or Ntfy.sh (all optional, any combination, sent in parallel)
- **AI-generated alert messages** — uses Groq (free), Anthropic Claude, or OpenAI to write calm, context-aware SMS-style messages in Swedish
- **Configurable active hours** — only monitors between e.g. 07:00–22:00
- **Cooldown logic** — prevents notification spam (configurable hours between repeated alerts)
- **Per-room awareness** — maps sensors to room names for natural language alerts
- **Auto-clear** — alert clears automatically when motion is detected again
- **Four entities per monitored person**:
  - `sensor.*_status` — active / inactive / alert / unknown
  - `sensor.*_last_seen` — timestamp of last motion
  - `sensor.*_last_room` — room where motion was last seen
  - `binary_sensor.*_alert` — on when alert is active (device_class: problem)

## Installation

### Via HACS (Custom Repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/wizz666/homeassistant-caregiver-mode` as **Integration**
3. Install **Caregiver Mode**
4. Restart Home Assistant

### Manual

Copy `custom_components/caregiver_mode/` to your HA config directory and restart.

## Configuration

Go to **Settings → Integrations → Add Integration → Caregiver Mode**.

The setup has three steps:

### Step 1 – Basic Settings
| Field | Description | Default |
|---|---|---|
| Person name | Name of the monitored person | Farmor |
| Active hours start | When to start monitoring (HH:MM) | 07:00 |
| Active hours end | When to stop monitoring (HH:MM) | 22:00 |
| Alert after X hours | Hours of inactivity before alert | 4 |
| Alert cooldown | Hours between repeated alerts | 6 |

### Step 2 – Sensors
Select one or more `binary_sensor` entities with device class `motion` or `occupancy`. Assign room names as a comma-separated list (matching sensor order).

### Step 3 – Notifications

At least one channel must be configured.

**HA Mobile App**
| Field | Example |
|---|---|
| Primary service | `notify.mobile_app_iphone` |
| Secondary service | `notify.mobile_app_samsung` (optional) |

**Telegram Bot**
| Field | Description |
|---|---|
| Bot token | From [@BotFather](https://t.me/BotFather) |
| Chat ID(s) | One or more IDs, comma-separated (`123456789, 987654321`) |

To get your chat ID: start the bot and visit `https://api.telegram.org/bot<TOKEN>/getUpdates`.

**Ntfy.sh**
| Field | Default |
|---|---|
| Topic | e.g. `farmor-larm-hemma` |
| Server URL | `https://ntfy.sh` (or self-hosted) |

Subscribe to your topic in the [Ntfy app](https://ntfy.sh/) (Android/iOS/web).

**AI Messages** (optional)
| Provider | Model | Notes |
|---|---|---|
| Groq | llama-3.1-8b-instant | Free tier available |
| Anthropic | claude-haiku-4-5 | Fast and cheap |
| OpenAI | gpt-4o-mini | Widely available |

Messages are written in Swedish and fall back to a plain-text template if the AI call fails.

## Example Alert Message

> Farmor registrerades senast i Köket kl 08:42. Det är nu 13:15 (onsdag) — 4h 33min utan rörelse.

With AI enabled:

> Farmor har inte rört sig sedan 08:42 i Köket. Det är nu halvtiden på eftermiddagen — kanske värt att ringa och höra hur det är?

## Integration icon (HA 2026.3+)

Starting with Home Assistant 2026.3, custom integrations can ship their own brand icons directly — no external PR needed.

Place your icon in:
```
custom_components/caregiver_mode/brand/icon.png
```

Optional variants: `dark_icon.png`, `logo.png`, `logo@2x.png`. Recommended size: 256×256 px PNG.

The `brand/` directory is already included in this repo (empty). Drop in your icon and restart HA.

## Stöd projektet

Gillar du det här projektet? En kopp kaffe uppskattas ☕

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/wizz666)

## License

MIT
