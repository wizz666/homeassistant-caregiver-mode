# Caregiver Mode for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-2.1.2-blue.svg)](https://github.com/wizz666/homeassistant-caregiver-mode/releases)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support_this_project-F16061?logo=ko-fi&logoColor=white)](https://ko-fi.com/wizz666)

🇸🇪 [Svenska](README.sv.md) | 🇬🇧 English

AI-assisted motion monitoring for elderly or vulnerable persons living independently. Caregiver Mode watches your motion sensors and sends contextual alerts — via the HA mobile app, Telegram, or Ntfy — if no activity is detected for a configurable number of hours.

**New in V2:** Optional camera-based fall detection powered by vision AI. When a fall is detected, a snapshot is saved, notifications are sent with the image, and the dashboard card shows the photo with a one-tap "Action taken" button.

## Features

- **Multi-channel notifications** — HA mobile app, Telegram Bot, and/or Ntfy.sh (all optional, any combination, sent in parallel)
- **AI-generated alert messages** — uses Groq (free), Anthropic Claude, or OpenAI to write calm, context-aware messages
- **Fall detection via camera** *(optional)* — periodic AI vision analysis detects a person lying on the floor; confirms across multiple frames before alerting
- **Snapshot on fall** — saves a camera image when a fall is confirmed; displayed in the dashboard card and sent via Telegram
- **Configurable active hours** — only monitors between e.g. 07:00–22:00
- **Cooldown logic** — prevents notification spam (configurable hours between repeated alerts)
- **Per-room awareness** — maps sensors to room names for natural language alerts
- **Departure detection** *(optional)* — detects when the person leaves home via door sensor + device tracker
- **Auto-clear** — alerts clear automatically when motion is detected again
- **Custom Lovelace card** — status card with live image display and "Action taken" button

## Entities

Per monitored person:

| Entity | Description |
|---|---|
| `sensor.*_status` | active / inactive / alert / unknown |
| `sensor.*_last_seen` | timestamp of last motion (formatted) |
| `sensor.*_last_room` | room where motion was last seen |
| `binary_sensor.*_alert` | on when inactivity alert is active |
| `binary_sensor.*_fall_detected` | on when fall is confirmed *(if camera configured)* |

## Installation

### Via HACS (Custom Repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/wizz666/homeassistant-caregiver-mode` as **Integration**
3. Install **Caregiver Mode**
4. Restart Home Assistant
5. Copy `www/caregiver-card.js` to your `/config/www/` folder
6. Add it as a Lovelace resource: **Settings → Dashboards → Resources → Add** `/local/caregiver-card.js` (type: JavaScript module)

### Manual

Copy `custom_components/caregiver_mode/` to your HA config directory, copy `www/caregiver-card.js` to `/config/www/`, and restart.

## Configuration

Go to **Settings → Integrations → Add Integration → Caregiver Mode**.

### Step 1 – Basic Settings

| Field | Description | Default |
|---|---|---|
| Person name | Name of the monitored person | Grandma |
| Active hours start | When to start monitoring (HH:MM) | 07:00 |
| Active hours end | When to stop monitoring (HH:MM) | 22:00 |
| Alert after X hours | Hours of inactivity before alert | 4 |
| Alert cooldown | Hours between repeated alerts | 6 |

### Step 2 – Sensors (Rooms)

Add one or more motion sensors and assign them to rooms. Each room gets a name used in alerts and the dashboard card.

### Step 3 – Notifications

At least one channel must be configured.

**HA Mobile App**
| Field | Example |
|---|---|
| Primary service | `notify.mobile_app_iphone` |
| Secondary service | `notify.mobile_app_tablet` (optional) |

**Telegram Bot**
| Field | Description |
|---|---|
| Bot token | From [@BotFather](https://t.me/BotFather) |
| Chat ID(s) | One or more IDs, comma-separated |

To get your chat ID: start the bot and visit `https://api.telegram.org/bot<TOKEN>/getUpdates`.

**Ntfy.sh**
| Field | Default |
|---|---|
| Topic | e.g. `grandma-alerts-home` |
| Server URL | `https://ntfy.sh` (or self-hosted) |

**AI Messages** (optional)
| Provider | Model | Notes |
|---|---|---|
| Groq | llama-3.1-8b-instant | Free tier, no credit card required |
| Anthropic | claude-haiku-4-5 | Fast and inexpensive |
| OpenAI | gpt-4o-mini | Widely available |

### Step 4 – Departure Detection *(optional)*

Detects when the person leaves home by combining door sensor events with a device tracker (phone).

| Field | Description |
|---|---|
| Device tracker | `device_tracker.phone` entity |
| Exit sensors | Door contact sensors |
| Departure check delay | Minutes to wait after door closes before checking (default: 5) |

### Step 5 – Fall Detection *(optional)*

Uses a camera and a vision AI model to detect falls. A snapshot is taken every 60 seconds during active hours and analyzed. N consecutive positive results (configurable) trigger an alert.

| Field | Description | Default |
|---|---|---|
| Camera entity | Any HA camera (e.g. Tapo, Frigate, generic) | — |
| Vision provider | groq / ollama / anthropic / openai | groq |
| API key | Leave empty to reuse the AI key from Step 3 if same provider | — |
| Groq vision model | Model name (update here if Groq changes their lineup) | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Ollama URL | Only for local Ollama | `http://localhost:11434` |
| Ollama model | Only for local Ollama | `moondream` |
| Confirmations required | Frames in a row before alert (1–5) | 2 |

**Groq** is recommended for most users — it has a free tier, no credit card required, and is fast.

## Dashboard Card

Add the custom Lovelace card to any dashboard:

```yaml
type: custom:caregiver-card
entity_prefix: grandma      # lowercase person name, spaces → underscore
name: Grandma               # display name
entry_id: <config_entry_id> # required for the "Action taken" button
```

To find your `config_entry_id`: **Settings → Integrations → Caregiver Mode → Configure** — the ID is visible in the browser URL as the last path segment.

When a fall is detected the card shows:
- A pulsing orange banner
- The camera snapshot taken at detection
- A green **"Action taken"** button that clears the alert and deletes the image

## Services

| Service | Description |
|---|---|
| `caregiver_mode.trigger_test_fall` | Simulate a fall alert (for testing notifications) |
| `caregiver_mode.trigger_test_alert` | Simulate an inactivity alert |
| `caregiver_mode.clear_fall` | Clear an active fall alert and delete the snapshot |

All services require `config_entry_id` — find it in the integration URL as described above.

## Example Alert Messages

Inactivity alert (no AI):
> Grandma was last seen in the Kitchen at 08:42. It is now 13:15 (Wednesday) — 4h 33min without motion.

With AI enabled:
> Grandma hasn't moved since 08:42 in the Kitchen. It's now mid-afternoon — might be worth giving her a call to check in?

Fall detection alert:
> 🚨 FALL DETECTED – Grandma may have fallen. The camera analysis showed a person lying on the floor. Please check immediately!

## Integration Icon (HA 2026.3+)

Starting with Home Assistant 2026.3, custom integrations can ship their own brand icons. Place your icon in:

```
custom_components/caregiver_mode/brand/icon.png
```

Optional variants: `dark_icon.png`, `logo.png`, `logo@2x.png`. Recommended size: 256×256 px PNG.

## Support

If you find this useful, a coffee is always appreciated ☕

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/wizz666)

## License

MIT
