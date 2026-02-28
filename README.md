# Caregiver Mode for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-3.0.0-blue.svg)](https://github.com/wizz666/homeassistant-caregiver-mode/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support_this_project-F16061?logo=ko-fi&logoColor=white)](https://ko-fi.com/wizz666)

🇸🇪 [Svenska](README.sv.md) | 🇬🇧 English

A Home Assistant integration for monitoring elderly or vulnerable persons living independently. Caregiver Mode watches your motion sensors and sends contextual alerts to family members if no activity is detected — before something becomes an emergency.

**V3.0 adds pattern learning:** the integration now studies the person's daily rhythm over time and can warn you earlier than a fixed time threshold ever could. If grandma always moves to the kitchen by 07:30 and it's 09:00 with no sign of life, you'll know — hours before the standard 4-hour alert would fire.

---

## How it works

```
Motion sensors  ──►  Caregiver Mode  ──►  HA mobile app
Door sensor     ──►  (learns rhythm)  ──►  Telegram
Camera          ──►  (detects fall)   ──►  Ntfy.sh
Phone tracker   ──►  (tracks exits)   ──►  any combination
```

The integration runs entirely within your Home Assistant instance. No cloud service is required for the core features. AI message generation and vision fall detection are optional and use external APIs only if you configure them.

---

## Feature overview

| Feature | Description |
|---|---|
| **Inactivity monitoring** | Alert if no motion for a configurable number of hours during active hours |
| **Pattern learning** *(V3)* | Learns the person's daily rhythm; computes an anomaly score (0–100) in real time |
| **Early warning** *(V3)* | Optional early alert when anomaly score exceeds a threshold — hours before the normal alert |
| **Weekly trend** *(V4)* | Detects gradual decline in activity level week over week — before a crisis develops |
| **"I'm OK" button** *(V4)* | The monitored person can press any Zigbee button to send a wellness confirmation and clear alerts |
| **Escalation chain** *(V4)* | If nobody responds to an alert within N minutes, a second alert goes to additional contacts |
| **Multi-channel notifications** | HA mobile app, Telegram Bot, Ntfy.sh — any combination, sent in parallel |
| **AI-generated messages** | Groq (free), Anthropic Claude, or OpenAI writes calm, context-aware alert text |
| **Fall detection** *(optional)* | Camera + vision AI detects a person lying on the floor; confirms across multiple frames |
| **Fall snapshot** | Camera image saved and sent when a fall is confirmed |
| **Departure detection** *(optional)* | Detects when the person leaves home via door sensor + phone tracker |
| **Per-room awareness** | Sensors mapped to room names for natural-language alerts |
| **Configurable active hours** | Only monitors between e.g. 07:00–22:00 |
| **Auto-clear** | Alerts clear automatically when motion resumes |
| **Custom dashboard card** | Status card with anomaly gauge, live image, and action buttons |
| **Bilingual** | English and Swedish notification messages |

---

## Entities

Per monitored person (replace `<name>` with the slug of the person's name):

| Entity | Description |
|---|---|
| `sensor.caregiver_<name>_status` | `active` / `inactive` / `alert` / `unknown` |
| `sensor.caregiver_<name>_last_seen` | Timestamp of last detected motion |
| `sensor.caregiver_<name>_last_room` | Room where motion was last seen |
| `sensor.caregiver_<name>_anomaly_score` | 0–100 pattern anomaly score (or `learning` during first 7 days); also exposes `weekly_trend` attribute |
| `binary_sensor.caregiver_<name>_alert` | `on` when an inactivity alert is active |
| `binary_sensor.caregiver_<name>_fall_detected` | `on` when a fall has been confirmed *(if camera configured)* |

The `anomaly_score` sensor has these extra attributes:

| Attribute | Description |
|---|---|
| `days_learned` | Number of days of history collected |
| `confidence` | `none` / `low` / `medium` / `high` |
| `expected_first_motion` | Predicted first movement time today (HH:MM) |
| `anomaly_reason` | Human-readable explanation of the current score |
| `weekly_trend` | `stable` / `slightly_declining` / `declining` / `improving` / `insufficient_data` |
| `trend_reason` | Plain-language explanation of the weekly trend |

---

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/wizz666/homeassistant-caregiver-mode` as type **Integration**
3. Search for **Caregiver Mode** and install it
4. Restart Home Assistant
5. Copy `www/caregiver-card.js` to your `/config/www/` folder
6. Register the Lovelace resource: **Settings → Dashboards → Resources → Add**
   - URL: `/local/caregiver-card.js`
   - Type: **JavaScript module**

### Manual

1. Copy `custom_components/caregiver_mode/` to your HA `/config/custom_components/` directory
2. Copy `www/caregiver-card.js` to `/config/www/`
3. Restart Home Assistant
4. Register the Lovelace resource as above

---

## Configuration

Go to **Settings → Integrations → Add Integration → Caregiver Mode**.

### Step 1 – Basic settings

| Field | Description | Default |
|---|---|---|
| Person name | Name of the monitored person (e.g. Grandma) | Grandma |
| Active hours start | When monitoring begins (HH:MM) | 07:00 |
| Active hours end | When monitoring ends (HH:MM) | 22:00 |
| Alert after X hours | Hours of inactivity before alert fires | 4 |
| Alert cooldown | Hours between repeated alerts | 6 |
| Notification language | `auto` follows your HA language setting | auto |

### Step 2 – Sensors and rooms

Add one or more motion sensors and assign each to a room. Room names appear in alert messages and on the dashboard card.

Example:
- **Bedroom** → `binary_sensor.pir_bedroom`
- **Kitchen** → `binary_sensor.pir_kitchen`, `binary_sensor.motion_fridge_area`
- **Bathroom** → `binary_sensor.pir_bathroom`

### Step 3 – Notifications

At least one notification channel must be configured.

**HA Mobile App**

| Field | Example |
|---|---|
| Primary service | `notify.mobile_app_iphone` |
| Secondary service | `notify.mobile_app_tablet` *(optional)* |

**Telegram Bot**

| Field | Description |
|---|---|
| Bot token | Create one at [@BotFather](https://t.me/BotFather) |
| Chat ID(s) | Comma-separated. Find yours: open the bot and visit `https://api.telegram.org/bot<TOKEN>/getUpdates` |

**Ntfy.sh**

| Field | Default |
|---|---|
| Topic | e.g. `grandma-alerts` |
| Server URL | `https://ntfy.sh` or your self-hosted instance |

**AI messages** *(optional)*

Replaces the default template message with a naturally worded sentence tailored to the situation.

| Provider | Model | Notes |
|---|---|---|
| Groq | llama-3.1-8b-instant | **Free**, no credit card required |
| Anthropic | claude-haiku-4-5 | Fast, ~$0.001 per alert |
| OpenAI | gpt-4o-mini | Widely available |

### Step 4 – Departure detection *(optional)*

Notifies family when the person leaves home. Combines a door contact sensor (detects the door opening and closing) with a device tracker (phone GPS).

| Field | Description |
|---|---|
| Device tracker | `person.grandma` or `device_tracker.phone` |
| Exit sensors | Front door, back door, etc. |
| Check delay | Minutes to wait after door closes before concluding departure (default: 5) |

Departure scenarios handled:
- Phone left home → notification
- Door opened + no indoor motion + phone away → confirmed departure
- Door opened + no indoor motion + phone still home → "may have forgotten phone"

### Step 5 – Fall detection *(optional)*

A snapshot is taken every 60 seconds during active hours and sent to a vision AI model. N consecutive positive results trigger a fall alert with a camera image.

| Field | Description | Default |
|---|---|---|
| Camera entity | Any HA camera (Tapo, Frigate, Ring, etc.) | — |
| Vision provider | groq / ollama / anthropic / openai | groq |
| API key | Leave empty to reuse the AI key from Step 3 | — |
| Groq vision model | Update here if Groq changes their lineup | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Ollama URL | Only for local Ollama | `http://localhost:11434` |
| Ollama model | Only for local Ollama | `moondream` |
| Confirmations required | Consecutive detections before alert (1–5) | 2 |

> **Groq** is recommended for most users — free tier, no credit card, typically ~2 second response time.

---

## Pattern Learning (V3.0)

Pattern learning observes the person's daily movement rhythm and computes an **anomaly score** every 5 minutes. The score is available as a sensor and can trigger early warning notifications.

### How it works

**You do not need to configure anything.** The integration starts collecting data automatically from day one. You never need to tell it when the person normally wakes up — it figures that out by itself.

The integration records two things each day:
- The time of the person's **first motion** (e.g. 07:27)
- Which **hours** had at least one motion event

Every night at 02:00 the data is finalized and a statistical model is computed per weekday (Mondays are compared to previous Mondays, Sundays to Sundays, and so on). After 7 days the anomaly sensor becomes active.

> **Pattern learning works alongside the regular inactivity alert — it does not replace it.** The standard alert (e.g. 4 hours of no motion) always remains active as a safety net. Pattern learning adds an *earlier* warning layer on top of that.

### Anomaly score calculation

The score is based on two checks, combined into a single 0–100 number every 5 minutes.

| Check | Weight | What it measures |
|---|---|---|
| First motion | 65% | How late the first movement of the day is compared to the person's usual time |
| Hourly activity | 35% | How many hours that normally have movement are silent today |

**First motion — how "late" is measured:**

The system tracks how much the person's wake time normally varies day to day (e.g. ±8 minutes). It then measures how far today's silence has gone past that normal range:

| Situation | Score |
|---|---|
| Motion already detected, or still within the normal window | 0 — normal |
| Late by 1–2× the usual variation (e.g. 8–16 min past normal) | 50 — slightly unusual |
| Late by 2–3× the usual variation | 80 — clearly late |
| Late by more than 3× the usual variation | 100 — very unusual |

In plain terms: if grandma normally wakes between 07:20–07:35 and it is 09:00 with no movement, that is far outside her normal range and scores high.

### Timeline

| Day | State |
|---|---|
| 1–6 | Sensor shows `learning`, data is collected |
| 7 | Sensor activates, anomaly score computed every 5 min |
| 14 | Confidence: `low` → `medium` |
| 30 | Confidence: `high` |
| 60 | History capped at 60 days (rolling window) |

### Example

Grandma normally wakes between 07:20–07:35 (mean 07:27, std 8 min):

| Time | Motion | Score | Reason |
|---|---|---|---|
| 07:00 | — | 0 | Within normal window |
| 07:35 | ✓ | 0 | First motion recorded |
| 09:00 | — (no motion all morning) | 82 | >2σ late + missed active hours |
| 09:15 | — | 90 | Score rising |

With a **threshold of 75**, an early warning fires at ~09:00 — roughly 2 hours and 27 minutes before the standard 4-hour inactivity alert would have triggered.

### Configuring pattern learning

Go to **Settings → Integrations → Caregiver Mode → Configure → Pattern learning**:

| Field | Description | Default |
|---|---|---|
| Enable pattern learning | Turn data collection and anomaly sensor on/off | on |
| Enable early warning alerts | Send notification when score exceeds threshold | off |
| Early warning threshold | Score level that triggers notification (50–100) | 75 |

Pattern data is stored in `/config/.storage/caregiver_pattern_<name>.json`.

---

## V4.0 features

### "I'm OK" button

Any button, Zigbee remote, or binary sensor in Home Assistant can serve as a wellness button. When the monitored person presses it:

- A confirmation notification is sent to all configured channels: *"Grandma pressed the 'I'm OK' button at 08:34. Everything is fine!"*
- Any active inactivity alert is cleared automatically
- The event is logged

**Configure:** Settings → Integrations → Caregiver Mode → Configure → **Wellness & escalation**

Enter the entity_id of the button (e.g. `button.bedroom_zigbee_button`). Works with any HA entity that changes state when pressed: `button.*`, `input_button.*`, Zigbee2MQTT sensors, or binary sensors.

---

### Escalation chain

If an alert fires but nobody in the family responds:

1. Primary alert sent immediately to all configured channels
2. After N minutes (default 15, configurable 5–60) — if the alert is still active — a second escalation notification is sent to **additional contacts**
3. Escalation is cancelled automatically if the person moves (alert clears)

The escalation message makes clear it is a second attempt: *"Alert was sent 15 min ago with no acknowledgement. Grandma was last seen in the Kitchen at 08:42. This escalation is being sent to additional contacts."*

**Configure:** Settings → Integrations → Caregiver Mode → Configure → **Wellness & escalation**

| Field | Description | Default |
|---|---|---|
| Escalation contacts | Comma-separated notify services (e.g. `notify.mobile_app_son,notify.mobile_app_daughter`) | — |
| Escalation delay | Minutes to wait before escalating (5–60) | 15 |

---

### Weekly activity trend

After 14 days of data the `anomaly_score` sensor gains two new attributes:

| Attribute | Values |
|---|---|
| `weekly_trend` | `stable` / `slightly_declining` / `declining` / `improving` / `insufficient_data` |
| `trend_reason` | Plain-language explanation, e.g. *"somewhat fewer active hours/day (7.2 vs 9.1); waking 22 min later than usual (08:12 vs 07:50)"* |

The trend compares the **last 7 days** against the **previous 7–21 days** on two metrics:
- Average number of hours per day with at least one motion event
- Average time of first motion

This can detect gradual decline weeks before a health event, and can be used in HA automations (e.g. send a weekly summary if trend is `declining`).

---

## Dashboard card

Add the custom Lovelace card to any dashboard:

```yaml
type: custom:caregiver-card
entity_prefix: grandma       # lowercase person name, spaces → underscore
name: Grandma                # display name
entry_id: <config_entry_id>  # required for action buttons
```

To find your `config_entry_id`: open **Settings → Integrations → Caregiver Mode → Configure** — the ID is the last segment in the browser URL.

The card shows:
- Current status with colour coding (green / grey / red)
- Time since last motion
- Last room
- Anomaly score bar (green → yellow → orange → red)
- Fall alert banner with camera snapshot and "Action taken" button
- Departure alert banner

---

## Test services

All services require `config_entry_id` (see above).

| Service | Description |
|---|---|
| `caregiver_mode.trigger_test_alert` | Simulate an inactivity alert (also triggers escalation timer if configured) |
| `caregiver_mode.trigger_test_fall` | Simulate a fall alert (captures a real snapshot if camera is configured) |
| `caregiver_mode.clear_fall` | Clear an active fall alert and delete the snapshot |

Use **Developer Tools → Services** to call them.

---

## Example alert messages

**Inactivity alert (no AI):**
> Grandma was last seen in the Kitchen at 08:42. It is now 13:15 (Wednesday) — 4h 33min without motion.

**Inactivity alert (AI enabled):**
> Grandma hasn't moved since 08:42 in the Kitchen. It's now mid-afternoon — might be worth giving her a call?

**Early warning (pattern learning):**
> ⚠️ Grandma has not been seen this morning. Expected first movement around 07:27. Current anomaly score: 84/100.

**Fall alert:**
> 🚨 FALL DETECTED – Grandma may have fallen. The camera analysis showed a person lying on the floor. Please check immediately! (13:07)

**Departure alert:**
> 🚶 Grandma has left home — door opened, no indoor motion, phone is away.

---

## Hardware guide and cost estimate

You can build a complete monitoring setup with off-the-shelf consumer hardware. Below are three tiers ranging from a minimal setup to a full installation with fall detection.

> Prices are approximate European retail prices (early 2026). Check local retailers and online marketplaces for current pricing.

### What you need to run Home Assistant

If you don't already have a Home Assistant server:

| Item | Example | Approx. cost |
|---|---|---|
| Single-board computer | Raspberry Pi 4 (2 GB) | €50–65 |
| Case + fan | Official RPi case or Argon ONE | €10–20 |
| Power supply | Official RPi USB-C PSU | €10 |
| microSD card | 32 GB Class 10 (or USB SSD) | €8–15 |
| **Total (server only)** | | **~€80–110** |

> A Raspberry Pi 4 with 2 GB RAM comfortably runs Home Assistant OS with Caregiver Mode and a dozen integrations. A used mini-PC (Intel NUC, etc.) is an alternative if you want more headroom.

### Zigbee USB adapter (required for Zigbee sensors)

| Item | Example | Approx. cost |
|---|---|---|
| Zigbee coordinator | SONOFF Zigbee 3.0 USB Dongle Plus | €15–20 |

Plug it into the RPi, install the Zigbee2MQTT or ZHA add-on in HA — no hub or subscription required.

---

### Tier 1 — Basic monitoring (motion only)

Suitable for a small apartment. Covers 3 rooms.

| Item | Quantity | Unit price | Total |
|---|---|---|---|
| Raspberry Pi 4 + accessories | 1 | €95 | €95 |
| Zigbee USB dongle | 1 | €18 | €18 |
| PIR motion sensor (Zigbee) | 3 | €12 | €36 |
| **Total** | | | **~€150** |

Recommended motion sensors: SONOFF SNZB-03P, Aqara P1, IKEA VALLHORN, or Philips Hue Motion.

**What you get:** inactivity alerts + pattern learning. After one week the system starts predicting grandma's rhythm and can alert you earlier than a fixed timer.

---

### Tier 2 — Standard (+ departure detection)

Adds a door contact sensor so the integration can detect when the person leaves home.

| Addition | Quantity | Unit price | Total |
|---|---|---|---|
| Door contact sensor (Zigbee) | 1 | €10 | €10 |
| **Tier 2 total** | | | **~€160** |

Recommended: SONOFF SNZB-04P, Aqara Door and Window Sensor, IKEA PARASOLL.

**What you get:** everything in Tier 1 + departure/return notifications.

---

### Tier 3 — Full (+ fall detection)

Adds a camera for AI-powered fall detection.

| Addition | Quantity | Unit price | Total |
|---|---|---|---|
| IP camera (indoor, 1080p) | 1 | €25–35 | €30 |
| **Tier 3 total** | | | **~€190** |

Recommended cameras: TP-Link Tapo C110 / C210, Reolink E1, Aqara G3.

**What you get:** everything in Tiers 1–2 + fall detection with camera snapshot sent to Telegram/HA.

> **Note:** The camera only stores snapshots locally on your HA server when a fall is detected. No continuous recording, no cloud upload.

---

### If you already have Home Assistant

If HA is already running, only the sensors and optional camera are needed:

| Setup | Sensors needed | Approx. cost |
|---|---|---|
| Motion only (3 rooms) | 3× PIR + Zigbee dongle (if not already paired) | €40–55 |
| + Departure detection | + 1 door sensor | €10 |
| + Fall detection | + 1 IP camera | €30 |
| **Full upgrade** | | **~€55–95** |

---

### Ongoing costs

| Item | Cost |
|---|---|
| Electricity (RPi 4, 24/7) | ~€3–5 / month |
| Groq API (AI messages + fall detection) | **Free** (generous free tier) |
| Telegram Bot | **Free** |
| Ntfy.sh | **Free** (self-hosted or ntfy.sh free plan) |
| HA Cloud (Nabu Casa, optional for remote access) | €6.50 / month |

You can run a complete setup — including AI-generated alerts and fall detection — at essentially **zero monthly cost** using the free tiers of Groq and Telegram.

---

## Privacy

- All motion and pattern data stays on your HA server.
- Camera snapshots are saved locally and deleted automatically when the alert is cleared.
- If AI messages are enabled, alert context (person name, room, time of day) is sent to the chosen AI provider. No images are sent unless fall detection uses a vision provider.
- Pattern data (movement times) never leaves your local network.

---

## Integration icon (HA 2026.3+)

Starting with Home Assistant 2026.3, custom integrations can ship their own brand icon. Place your image in:

```
custom_components/caregiver_mode/brand/icon.png
```

Optional variants: `dark_icon.png`, `logo.png`, `logo@2x.png`. Recommended size: 256×256 px PNG.

---

## Support

If you find this useful, a coffee is always appreciated ☕

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/wizz666)

---

## License

MIT
