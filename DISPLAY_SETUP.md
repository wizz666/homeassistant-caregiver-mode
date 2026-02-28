# CYD Display Setup Guide

**Caregiver Mode — ESP32-2432S028 "Cheap Yellow Display"**

This guide takes you from an out-of-the-box CYD display to a live family dashboard showing your monitored person's status, anomaly score, and activity trend — with a touch button for "I'm OK" wellness confirmation.

---

## What you need

| Item | Notes |
|------|-------|
| ESP32-2432S028 ("CYD") | The standard version with ILI9341 display + XPT2046 touch |
| USB-C or Micro-USB cable | Depends on your board variant — bring both |
| A computer (Windows/Mac/Linux) | For the initial flash via browser |
| Your Home Assistant already running | With Caregiver Mode v4.0+ installed |

> **3D printed case?** Browse ready-made designs here:
> https://makerworld.com/sv/search/models?keyword=cyd%20case

---

## Step 1 — Install the CH340 USB driver (Windows only)

The CYD uses a CH340 USB-to-serial chip. On Windows 10/11 it may install automatically. If your PC doesn't detect the board:

1. Download: https://www.wch-ic.com/downloads/CH341SER_EXE.html
2. Run the installer, click **INSTALL**, then **OK**
3. Plug in the CYD — Windows should now show a COM port

Mac and Linux users: no driver needed.

---

## Step 2 — Flash ESPHome via browser (no software to install)

1. Open **Google Chrome** or **Microsoft Edge** (other browsers don't support Web Serial)
2. Go to: https://web.esphome.io
3. Click **Connect** → select the CYD's COM/USB port
4. Click **Prepare for first use** → ESPHome installs a minimal firmware
5. Done — the board is now ready for your real configuration

> If you already have ESPHome add-on in Home Assistant, you can skip step 2 and add the device directly via the add-on instead (see step 4 alternative).

---

## Step 3 — Create your secrets

Open your ESPHome `secrets.yaml` (or the ESPHome add-on's Secrets section) and add:

```yaml
wifi_ssid: "Your WiFi name"
wifi_password: "Your WiFi password"
caregiver_display_api_key: ""      # leave blank — ESPHome will generate one
caregiver_display_ota_password: "change_me_123"
```

> **Tip**: `caregiver_display_api_key` can be left blank the first time. ESPHome will generate a random key and show it after the first successful compile. Copy it back into secrets.yaml for future updates.

---

## Step 4 — Customize the display configuration

Copy `caregiver_display.yaml` to your ESPHome configuration folder (or paste it into the ESPHome web editor).

**Only three lines need to change:**

```yaml
substitutions:
  person_slug:      farmor       # ← the slug from your HA entities
  person_name:      Farmor       # ← name shown on screen
  wellness_entity:  input_button.caregiver_farmor_wellness  # ← HA helper (see Step 5)
```

**How to find your `person_slug`:**
In Home Assistant → Developer Tools → States, search for `caregiver_`. You'll see entities like `sensor.caregiver_farmor_status`. The part after `caregiver_` and before `_status` is your slug (in this example: `farmor`).

### ESPHome add-on alternative (step 2 + 4 combined)

If you use the ESPHome add-on in Home Assistant:
1. ESPHome → **+ New device** → name it `caregiver-display`
2. Paste the contents of `caregiver_display.yaml` (replacing what ESPHome generated)
3. Edit the three substitution lines
4. Click **Save** → **Install** → **Plug into this computer** → follow the prompts

---

## Step 5 — Create the "I'm OK" button in Home Assistant (optional)

The touch button on the display calls a Home Assistant `input_button` entity when pressed. This is optional — if you don't want touch, just leave `wellness_entity` blank.

**To create the entity:**

1. Home Assistant → **Settings → Helpers → + Create helper**
2. Type: **Button**
3. Name: `Caregiver Farmor Wellness` (use your person's name)
4. Entity ID will auto-set to: `input_button.caregiver_farmor_wellness`
5. Click **Create**

**Link it to Caregiver Mode:**
1. Settings → Integrations → Caregiver Mode → **Configure**
2. Open the **Wellness & Escalation** section
3. Paste the entity ID: `input_button.caregiver_farmor_wellness`
4. Save

Now when the person touches the display button, Caregiver Mode receives it as a wellness confirmation, clears any active alerts, and notifies the family.

---

## Step 6 — Flash the display

**Via ESPHome add-on:**
1. Click **Install** on your device
2. Choose **Wirelessly** if the board is already on WiFi, or **Plug into this computer** for first flash
3. Wait for the compile + upload (2–4 minutes)
4. The display should light up with your person's name

**Via web (esphome.io):**
1. Compile the YAML locally or via a CI action to get a `.bin` file
2. At https://web.esphome.io → Connect → **Install** → browse to the `.bin` file

---

## Step 7 — Verify in Home Assistant

1. After a minute, the CYD should appear under **Settings → Devices** as `Caregiver Display`
2. You'll see a `Backlight` light entity — use it to dim the display at night
3. The display updates immediately when any sensor value changes, plus a 30-second fallback refresh

---

## Display layout (320 × 240 landscape)

```
┌─────────────────────────────────────────────────────────────┐
│  Farmor                          ● Active         17:42     │  ← header (status color)
├─────────────────────────────────────────────────────────────┤
│  Last seen:   Just now                                       │
│  Last room:   Kitchen                                        │
│──────────────────────────────────────────────────────────── │
│  Anomaly:  [████████░░░░░░░░░░░░] 42                        │  ← green/orange/red bar
│  Trend:    Stable                                            │
│──────────────────────────────────────────────────────────── │
│                   [ I'm OK  ✓ ]                              │  ← touch button
└─────────────────────────────────────────────────────────────┘
```

**Header colors:**
- Dark green — active (recent motion)
- Dark gray — inactive (no motion, outside alert hours)
- Dark red — alert or fall detected

**Anomaly bar colors:**
- Green (0–49) — normal activity
- Orange (50–79) — slightly unusual
- Red (80–100) — significant deviation, check in

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Display stays black | Check backlight entity in HA — set to 80%. Also verify GPIO21 is connected |
| Touch not working | Try adding `mirror_x: true` or `mirror_y: true` in the `transform:` section |
| Touch offset/wrong area | Adjust `x_min`/`x_max`/`y_min`/`y_max` calibration values |
| Sensors show `—` | The entity names don't match your slug — double-check `person_slug` substitution |
| Can't compile | Make sure you're on ESPHome 2024.x or newer (supports `ili9xxx` + `gfonts://`) |
| WiFi fallback AP | Connect to "Caregiver Display" AP → visit 192.168.4.1 to reconfigure WiFi |

---

## Night dimming (optional automation)

Add this automation in Home Assistant to dim the display at night:

```yaml
- alias: "Caregiver Display – Night dim"
  trigger:
    - platform: time
      at: "22:00:00"
  action:
    - service: light.turn_on
      target:
        entity_id: light.caregiver_display_backlight
      data:
        brightness_pct: 20

- alias: "Caregiver Display – Morning bright"
  trigger:
    - platform: time
      at: "07:00:00"
  action:
    - service: light.turn_on
      target:
        entity_id: light.caregiver_display_backlight
      data:
        brightness_pct: 80
```

---

*Part of [Caregiver Mode](https://github.com/wizz666/homeassistant-caregiver-mode) — AI-powered home monitoring for vulnerable persons.*
