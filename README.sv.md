# Caregiver Mode för Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-2.1.2-blue.svg)](https://github.com/wizz666/homeassistant-caregiver-mode/releases)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Stöd_projektet-F16061?logo=ko-fi&logoColor=white)](https://ko-fi.com/wizz666)

🇬🇧 [English](README.md)

AI-assisterad rörelsesensorövervakning för äldre eller sårbar person som bor ensam. Caregiver Mode bevakar dina rörelsesensorer och skickar kontextuella larm — via HA-appen, Telegram eller Ntfy — om ingen aktivitet registreras under ett konfigurerbart antal timmar.

**Nytt i V2:** Valfri kamerabaserad falldetektering med vision-AI. När ett fall bekräftas sparas en bild, notiser skickas med foto, och dashboardkortet visar bilden med en "Åtgärd vidtagen"-knapp.

## Funktioner

- **Flera notiskanaler** — HA-mobilapp, Telegram Bot och/eller Ntfy.sh (alla valfria, valfri kombination, skickas parallellt)
- **AI-genererade larmmeddelanden** — använder Groq (gratis), Anthropic Claude eller OpenAI för att skriva lugna, kontextmedvetna meddelanden på svenska
- **Falldetektering via kamera** *(valfritt)* — periodisk vision-AI-analys detekterar en person liggande på golvet; bekräftar över flera bilder innan larm skickas
- **Snapshot vid fall** — sparar en kamerabild när fall bekräftas; visas i dashboardkortet och skickas via Telegram
- **Konfigurerbar aktiv tid** — övervakar bara mellan t.ex. 07:00–22:00
- **Cooldown-logik** — förhindrar notis-spam (konfigurerbart antal timmar mellan upprepade larm)
- **Rumsmedvetenhet** — kopplar sensorer till rumsnamn för naturliga larmtexter
- **Avgångsdetektion** *(valfritt)* — upptäcker när personen lämnar hemmet via dörrsensor + device tracker
- **Auto-rensning** — larm rensas automatiskt när rörelse registreras igen
- **Eget Lovelace-kort** — statuskort med livebild och "Åtgärd vidtagen"-knapp

## Entiteter

Per övervakad person:

| Entitet | Beskrivning |
|---|---|
| `sensor.*_status` | active / inactive / alert / unknown |
| `sensor.*_last_seen` | tidpunkt för senaste rörelse (formaterad) |
| `sensor.*_last_room` | rum där rörelse senast registrerades |
| `binary_sensor.*_alert` | on när inaktivitetslarm är aktivt |
| `binary_sensor.*_fall_detected` | on när fall bekräftats *(om kamera konfigurerad)* |

## Installation

### Via HACS (Custom Repository)

1. HACS → Integrationer → ⋮ → Anpassade arkiv
2. Lägg till `https://github.com/wizz666/homeassistant-caregiver-mode` som **Integration**
3. Installera **Caregiver Mode**
4. Starta om Home Assistant
5. Kopiera `www/caregiver-card.js` till din `/config/www/`-mapp
6. Lägg till som Lovelace-resurs: **Inställningar → Dashboards → Resurser → Lägg till** `/local/caregiver-card.js` (typ: JavaScript-modul)

### Manuell installation

Kopiera `custom_components/caregiver_mode/` till din HA config-katalog, kopiera `www/caregiver-card.js` till `/config/www/`, och starta om.

## Konfiguration

Gå till **Inställningar → Integrationer → Lägg till integration → Caregiver Mode**.

### Steg 1 – Grundinställningar

| Fält | Beskrivning | Standard |
|---|---|---|
| Personnamn | Namnet på den övervakade personen | Farmor |
| Aktiva timmar start | När övervakning börjar (HH:MM) | 07:00 |
| Aktiva timmar slut | När övervakning slutar (HH:MM) | 22:00 |
| Larm efter X timmar | Timmars inaktivitet innan larm | 4 |
| Larm-cooldown | Timmar mellan upprepade larm | 6 |

### Steg 2 – Sensorer (Rum)

Lägg till en eller flera rörelsesensorer och tilldela dem till rum. Varje rum får ett namn som används i larmtexter och dashboardkortet.

### Steg 3 – Notiser

Minst en kanal måste konfigureras.

**HA-mobilapp**
| Fält | Exempel |
|---|---|
| Primär tjänst | `notify.mobile_app_iphone` |
| Sekundär tjänst | `notify.mobile_app_samsung` (valfri) |

**Telegram Bot**
| Fält | Beskrivning |
|---|---|
| Bot-token | Från [@BotFather](https://t.me/BotFather) |
| Chat-ID(n) | Ett eller flera ID, kommaseparerade |

För att hitta ditt chat-ID: starta boten och besök `https://api.telegram.org/bot<TOKEN>/getUpdates`.

**Ntfy.sh**
| Fält | Standard |
|---|---|
| Topic | t.ex. `farmor-larm-hemma` |
| Server-URL | `https://ntfy.sh` (eller självhostad) |

**AI-meddelanden** (valfritt)
| Leverantör | Modell | Notering |
|---|---|---|
| Groq | llama-3.1-8b-instant | Gratis, inget kreditkort krävs |
| Anthropic | claude-haiku-4-5 | Snabb och billig |
| OpenAI | gpt-4o-mini | Vanligt tillgänglig |

Meddelanden genereras på svenska och faller tillbaka på en generisk textmall om AI-anropet misslyckas.

### Steg 4 – Avgångsdetektion *(valfritt)*

Detekterar när personen lämnar hemmet genom att kombinera dörrsensorhändelser med en device tracker (telefon).

| Fält | Beskrivning |
|---|---|
| Device tracker | `device_tracker.telefon`-entitet |
| Utgångssensorer | Dörrkontaktsensorer |
| Fördröjning | Minuter att vänta efter att dörren stängs innan kontroll (standard: 5) |

### Steg 5 – Falldetektering *(valfritt)*

Använder en kamera och en vision-AI-modell för att detektera fall. En bild tas var 60:e sekund under aktiva timmar och analyseras. N positiva svar i rad (konfigurerbart) utlöser ett larm.

| Fält | Beskrivning | Standard |
|---|---|---|
| Kameraentitet | Valfri HA-kamera (t.ex. Tapo, Frigate) | — |
| Vision-leverantör | groq / ollama / anthropic / openai | groq |
| API-nyckel | Lämna tom för att återanvända AI-nyckeln från Steg 3 om samma leverantör | — |
| Groq vision-modell | Modellnamn (uppdatera här om Groq byter) | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Ollama-URL | Bara för lokal Ollama | `http://localhost:11434` |
| Ollama-modell | Bara för lokal Ollama | `moondream` |
| Bekräftelser krävs | Bilder i rad innan larm (1–5) | 2 |

**Groq** rekommenderas för de flesta — gratis tier, inget kreditkort, och snabbt.

## Dashboard-kort

Lägg till det egna Lovelace-kortet i valfri dashboard:

```yaml
type: custom:caregiver-card
entity_prefix: farmor        # personnamnet med gemener, mellanslag → understreck
name: Farmor                 # visningsnamn
entry_id: <config_entry_id>  # krävs för "Åtgärd vidtagen"-knappen
```

För att hitta ditt `config_entry_id`: **Inställningar → Integrationer → Caregiver Mode → Konfigurera** — ID:t syns i webbläsarens URL som det sista path-segmentet.

När ett fall detekteras visar kortet:
- En pulserande orange banner
- Kamerabilden tagen vid detekteringstillfället
- En grön **"✓ Åtgärd vidtagen — Stäng larm"**-knapp som rensar larmet och raderar bilden

## Tjänster

| Tjänst | Beskrivning |
|---|---|
| `caregiver_mode.trigger_test_fall` | Simulera ett falllarm (för att testa notiser) |
| `caregiver_mode.trigger_test_alert` | Simulera ett inaktivitetslarm |
| `caregiver_mode.clear_fall` | Rensa ett aktivt falllarm och radera snapshot |

Alla tjänster kräver `config_entry_id` — se ovan hur du hittar det.

## Exempel på larmmeddelanden

Inaktivitetslarm (utan AI):
> Farmor registrerades senast i Köket kl 08:42. Det är nu 13:15 (onsdag) — 4h 33min utan rörelse.

Med AI aktiverat:
> Farmor har inte rört sig sedan 08:42 i Köket. Det är nu halvtiden på eftermiddagen — kanske värt att ringa och höra hur det är?

Falllarm:
> 🚨 FALL DETEKTERAT – Farmor kan ha fallit. Kameraanalysen visade en person liggande på golvet. Kontrollera omedelbart!

## Integration-ikon (HA 2026.3+)

Från och med Home Assistant 2026.3 kan egna integrationer inkludera egna varumärkesikoner. Placera din ikon i:

```
custom_components/caregiver_mode/brand/icon.png
```

Valfria varianter: `dark_icon.png`, `logo.png`, `logo@2x.png`. Rekommenderad storlek: 256×256 px PNG.

## Stöd projektet

Gillar du det här projektet? En kopp kaffe uppskattas ☕

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/wizz666)

## Licens

MIT
