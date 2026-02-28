# Caregiver Mode för Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)](https://github.com/wizz666/homeassistant-caregiver-mode/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Stöd_projektet-F16061?logo=ko-fi&logoColor=white)](https://ko-fi.com/wizz666)

🇬🇧 [English](README.md) | 🇸🇪 Svenska

En Home Assistant-integration för att övervaka äldre eller sårbar person som bor ensam. Caregiver Mode bevakar dina rörelsesensorer och skickar kontextuella larm till familjemedlemmar om ingen aktivitet registreras — innan något hinner bli en nödsituation.

**V3.0 tillför mönsterinlärning:** integrationen studerar nu personens dygnsrytm över tid och kan varna dig tidigare än vad en fast tidsgräns någonsin klarar. Om farmor alltid rör sig till köket 07:30 och klockan är 09:00 utan livstecken — vet du om det — timmar innan standardlarmet på 4 timmar skulle ha gått.

---

## Hur det fungerar

```
Rörelsesensorer  ──►  Caregiver Mode  ──►  HA-mobilapp
Dörrsensor       ──►  (lär sig rytm)  ──►  Telegram
Kamera           ──►  (detekterar fall) ──►  Ntfy.sh
Telefon-tracker  ──►  (spårar utgång) ──►  valfri kombination
```

Integrationen körs helt inuti din Home Assistant-instans. Ingen molntjänst krävs för grundfunktionerna. AI-meddelandegenerering och vision-falldetektering är valfria och använder externa API:er bara om du konfigurerar dem.

---

## Funktionsöversikt

| Funktion | Beskrivning |
|---|---|
| **Inaktivitetsövervakning** | Larm om ingen rörelse under konfigurerbart antal timmar inom aktiva timmar |
| **Mönsterinlärning** *(V3)* | Lär sig personens dygnsrytm; beräknar avvikelsespoäng (0–100) i realtid |
| **Tidig varning** *(V3)* | Valfri tidig notis när avvikelsespoängen överstiger ett tröskelvärde — timmar före normalt larm |
| **Veckotrender** *(V4)* | Detekterar gradvis nedgång i aktivitetsnivå vecka för vecka — innan en kris uppstår |
| **"Jag mår bra"-knapp** *(V4)* | Personen kan trycka på valfri Zigbee-knapp för att skicka en välmåendebekräftelse och rensa larm |
| **Eskaleringstrappa** *(V4)* | Om ingen svarar på larmet inom N minuter skickas ett andra larm till ytterligare kontakter |
| **Flera notiskanaler** | HA-mobilapp, Telegram Bot, Ntfy.sh — valfri kombination, skickas parallellt |
| **AI-genererade meddelanden** | Groq (gratis), Anthropic Claude eller OpenAI skriver lugna, kontextmedvetna larmtexter |
| **Falldetektering** *(valfritt)* | Kamera + vision-AI detekterar en person liggande på golvet; bekräftar över flera bilder |
| **Fall-snapshot** | Kamerabild sparas och skickas när fall bekräftats |
| **Avgångsdetektion** *(valfritt)* | Registrerar när personen lämnar hemmet via dörrsensor + telefon-tracker |
| **Rumsmedvetenhet** | Sensorer kopplade till rumsnamn för naturliga larmtexter |
| **Konfigurerbar aktiv tid** | Övervakar bara mellan t.ex. 07:00–22:00 |
| **Auto-rensning** | Larm rensas automatiskt när rörelse registreras igen |
| **Eget dashboard-kort** | Statuskort med avvikelsemätare, livebild och åtgärdsknappar |
| **Tvåspråkigt** | Larmmeddelanden på engelska och svenska |

---

## Entiteter

Per övervakad person (ersätt `<namn>` med sluggen för personens namn):

| Entitet | Beskrivning |
|---|---|
| `sensor.caregiver_<namn>_status` | `active` / `inactive` / `alert` / `unknown` |
| `sensor.caregiver_<namn>_last_seen` | Tidpunkt för senaste registrerade rörelse |
| `sensor.caregiver_<namn>_last_room` | Rum där rörelse senast registrerades |
| `sensor.caregiver_<namn>_anomaly_score` | Avvikelsespoäng 0–100 (eller `learning` under första 7 dagarna); exponerar även attributet `weekly_trend` |
| `binary_sensor.caregiver_<namn>_alert` | `on` när inaktivitetslarm är aktivt |
| `binary_sensor.caregiver_<namn>_fall_detected` | `on` när fall bekräftats *(om kamera konfigurerad)* |

Sensorn `anomaly_score` har dessa extra attribut:

| Attribut | Beskrivning |
|---|---|
| `days_learned` | Antal dagar med insamlad historik |
| `confidence` | `none` / `low` / `medium` / `high` |
| `expected_first_motion` | Förväntad tid för första rörelse idag (HH:MM) |
| `anomaly_reason` | Läsbar förklaring till aktuell poäng |
| `weekly_trend` | `stable` / `slightly_declining` / `declining` / `improving` / `insufficient_data` |
| `trend_reason` | Förklaring av veckotrenden med klartext |

---

## Installation

### Via HACS (rekommenderas)

1. Öppna HACS → Integrationer → ⋮ → **Anpassade arkiv**
2. Lägg till `https://github.com/wizz666/homeassistant-caregiver-mode` som typ **Integration**
3. Sök efter **Caregiver Mode** och installera
4. Starta om Home Assistant
5. Kopiera `www/caregiver-card.js` till din `/config/www/`-mapp
6. Registrera Lovelace-resursen: **Inställningar → Dashboards → Resurser → Lägg till**
   - URL: `/local/caregiver-card.js`
   - Typ: **JavaScript-modul**

### Manuell installation

1. Kopiera `custom_components/caregiver_mode/` till din HA:s `/config/custom_components/`-katalog
2. Kopiera `www/caregiver-card.js` till `/config/www/`
3. Starta om Home Assistant
4. Registrera Lovelace-resursen enligt ovan

---

## Konfiguration

Gå till **Inställningar → Integrationer → Lägg till integration → Caregiver Mode**.

### Steg 1 – Grundinställningar

| Fält | Beskrivning | Standard |
|---|---|---|
| Personnamn | Den övervakade personens namn (t.ex. Farmor) | Grandma |
| Aktiva timmar start | När övervakning börjar (HH:MM) | 07:00 |
| Aktiva timmar slut | När övervakning slutar (HH:MM) | 22:00 |
| Larm efter X timmar | Timmars inaktivitet innan larm | 4 |
| Larm-cooldown | Timmar mellan upprepade larm | 6 |
| Notispråk | `auto` följer din HA:s språkinställning | auto |

### Steg 2 – Sensorer och rum

Lägg till en eller flera rörelsesensorer och tilldela varje sensor till ett rum. Rumsnamnen syns i larmtexter och på dashboardkortet.

Exempel:
- **Sovrum** → `binary_sensor.pir_sovrum`
- **Kök** → `binary_sensor.pir_kok`, `binary_sensor.motion_kylskap`
- **Badrum** → `binary_sensor.pir_badrum`

### Steg 3 – Notiser

Minst en notiskanal måste konfigureras.

**HA-mobilapp**

| Fält | Exempel |
|---|---|
| Primär tjänst | `notify.mobile_app_iphone` |
| Sekundär tjänst | `notify.mobile_app_samsung` *(valfri)* |

**Telegram Bot**

| Fält | Beskrivning |
|---|---|
| Bot-token | Skapa via [@BotFather](https://t.me/BotFather) |
| Chat-ID(n) | Kommaseparerade. Hitta ditt: starta boten och besök `https://api.telegram.org/bot<TOKEN>/getUpdates` |

**Ntfy.sh**

| Fält | Standard |
|---|---|
| Topic | t.ex. `farmor-larm` |
| Server-URL | `https://ntfy.sh` eller din självhostade instans |

**AI-meddelanden** *(valfritt)*

Ersätter standardmallen med en naturligt formulerad mening anpassad till situationen.

| Leverantör | Modell | Notering |
|---|---|---|
| Groq | llama-3.1-8b-instant | **Gratis**, inget kreditkort krävs |
| Anthropic | claude-haiku-4-5 | Snabb, ~0,01 kr per larm |
| OpenAI | gpt-4o-mini | Vanligt tillgänglig |

### Steg 4 – Avgångsdetektion *(valfritt)*

Meddelar familjen när personen lämnar hemmet. Kombinerar en dörrkontaktsensor (registrerar att dörren öppnats och stängts) med en device tracker (telefon-GPS).

| Fält | Beskrivning |
|---|---|
| Device tracker | `person.farmor` eller `device_tracker.telefon` |
| Utgångssensorer | Entrédörr, bakdörr, m.m. |
| Kontrollförsening | Minuter att vänta efter att dörren stängs innan slutsats dras (standard: 5) |

Hanterade avgångsscenarier:
- Telefonen lämnade hemmet → notis
- Dörr öppnad + ingen rörelse inomhus + telefonen borta → bekräftad avgång
- Dörr öppnad + ingen rörelse inomhus + telefonen kvar → "kan ha glömt telefonen"

### Steg 5 – Falldetektering *(valfritt)*

En bild tas var 60:e sekund under aktiva timmar och skickas till en vision-AI-modell. N positiva svar i rad utlöser ett falllarm med kamerabild.

| Fält | Beskrivning | Standard |
|---|---|---|
| Kameraentitet | Valfri HA-kamera (Tapo, Frigate, Ring, m.fl.) | — |
| Vision-leverantör | groq / ollama / anthropic / openai | groq |
| API-nyckel | Lämna tom för att återanvända AI-nyckeln från Steg 3 | — |
| Groq vision-modell | Uppdatera här om Groq byter modellnamn | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Ollama-URL | Bara för lokal Ollama | `http://localhost:11434` |
| Ollama-modell | Bara för lokal Ollama | `moondream` |
| Bekräftelser krävs | Bilder i rad innan larm (1–5) | 2 |

> **Groq** rekommenderas för de flesta — gratis tier, inget kreditkort, typiskt ~2 sekunders svarstid.

---

## Mönsterinlärning (V3.0)

Mönsterinlärning observerar personens dagliga rörelsemönster och beräknar en **avvikelsespoäng** var 5:e minut. Poängen visas som sensor och kan utlösa tidiga varningsnotiser.

### Hur det fungerar

**Du behöver inte konfigurera något.** Integrationen börjar samla in data automatiskt från dag ett. Du behöver aldrig tala om när personen brukar vakna — det räknar systemet ut själv.

Varje dag registreras två saker:
- Klockslaget för personens **första rörelse** (t.ex. 07:27)
- Vilka **timmar** som hade minst en rörelsehändelse

Varje natt kl 02:00 finaliseras data och en statistisk modell beräknas per veckodag (måndagar jämförs med tidigare måndagar, söndagar med söndagar osv). Efter 7 dagar aktiveras anomalysensorn.

> **Mönsterinlärning fungerar parallellt med det vanliga inaktivitetslarmet — det ersätter det inte.** Standardlarmet (t.ex. 4 timmars inaktivitet) är alltid aktivt som säkerhetsnät. Mönsterinlärning lägger till ett *tidigare* varningslager ovanpå det.

### Beräkning av avvikelsespoäng

Poängen baseras på två kontroller som kombineras till ett enda tal 0–100 var 5:e minut.

| Kontroll | Vikt | Vad den mäter |
|---|---|---|
| Första rörelse | 65% | Hur sent dagens första rörelse är jämfört med personens vanliga tid |
| Timaktivitet | 35% | Hur många timmar som normalt har rörelse men är tysta idag |

**Första rörelse — hur "sent" mäts:**

Systemet håller koll på hur mycket personens vakentid varierar från dag till dag (t.ex. ±8 minuter). Det mäter sedan hur långt utanför det normala spridningsmåttet dagens tystnad har gått:

| Situation | Poäng |
|---|---|
| Rörelse redan registrerad, eller fortfarande inom normalt fönster | 0 — normalt |
| Sent med 1–2× den vanliga variationen (t.ex. 8–16 min efter normalt) | 50 — lite ovanligt |
| Sent med 2–3× den vanliga variationen | 80 — klart sent |
| Sent med mer än 3× den vanliga variationen | 100 — mycket ovanligt |

Enkelt uttryckt: om farmor normalt rör sig 07:20–07:35 och klockan är 09:00 utan aktivitet — är det långt utanför hennes normala mönster och ger hög poäng.

### Tidslinje

| Dag | Status |
|---|---|
| 1–6 | Sensor visar `learning`, data samlas in |
| 7 | Sensor aktiveras, avvikelsespoäng beräknas var 5:e min |
| 14 | Confidence: `low` → `medium` |
| 30 | Confidence: `high` |
| 60 | Max 60 dagars historik (rullande fönster) |

### Exempel

Farmor vaknar normalt 07:20–07:35 (medelvärde 07:27, std 8 min):

| Tid | Rörelse | Poäng | Förklaring |
|---|---|---|---|
| 07:00 | — | 0 | Inom normalt fönster |
| 07:35 | ✓ | 0 | Första rörelse registrerad |
| 09:00 | — (ingen rörelse hela morgonen) | 82 | >2σ sent + missade aktiva timmar |
| 09:15 | — | 90 | Poängen stiger |

Med ett **tröskelvärde på 75** skickas en tidig varning runt 09:00 — ungefär 2 timmar och 27 minuter innan det vanliga 4-timmarslarmet hade gått.

### Konfigurera mönsterinlärning

Gå till **Inställningar → Integrationer → Caregiver Mode → Konfigurera → Mönsterinlärning**:

| Fält | Beskrivning | Standard |
|---|---|---|
| Aktivera mönsterinlärning | Slå på/av datainsamling och anomalysensor | på |
| Aktivera tidiga varningsnotiser | Skicka notis när poängen överstiger tröskeln | av |
| Tröskel för tidig varning | Poängnivå som utlöser notis (50–100) | 75 |

Mönsterdata sparas i `/config/.storage/caregiver_pattern_<namn>.json`.

---

## V4.0-funktioner

### "Jag mår bra"-knapp

Vilken knapp, Zigbee-fjärrkontroll eller binär sensor som helst i Home Assistant kan fungera som välmåendeknapp. När den övervakade personen trycker:

- En bekräftelsenotis skickas till alla konfigurerade kanaler: *"Farmor tryckte på 'Jag mår bra'-knappen kl 08:34. Allt är bra!"*
- Aktivt inaktivitetslarm rensas automatiskt
- Händelsen loggas

**Konfigurera:** Inställningar → Integrationer → Caregiver Mode → Konfigurera → **Välmående & eskalering**

Ange entity_id för knappen (t.ex. `button.sovrum_zigbeeknapp`). Fungerar med alla HA-entiteter som byter state vid tryckning: `button.*`, `input_button.*`, Zigbee2MQTT-sensorer eller binary_sensor.

---

### Eskaleringstrappa

Om ett larm skickas men ingen i familjen svarar:

1. Primärt larm skickas omedelbart till alla konfigurerade kanaler
2. Efter N minuter (standard 15, konfigurerbart 5–60) — om larmet fortfarande är aktivt — skickas ett andra larm till **ytterligare kontakter**
3. Eskalering avbryts automatiskt om personen rör sig (larmet rensas)

Eskaleringsmeddelandet gör tydligt att det är ett andra försök: *"Larm skickades för 15 min sedan utan respons. Farmor sågs senast i Köket kl 08:42. Detta eskaleringsmeddelande skickas till ytterligare kontakter."*

**Konfigurera:** Inställningar → Integrationer → Caregiver Mode → Konfigurera → **Välmående & eskalering**

| Fält | Beskrivning | Standard |
|---|---|---|
| Eskaleringskon­takter | Kommaseparerade notify-tjänster (t.ex. `notify.mobile_app_son,notify.mobile_app_dotter`) | — |
| Eskaleringsfördröjning | Minuter att vänta innan eskalering (5–60) | 15 |

---

### Veckotrender

Efter 14 dagars data får sensorn `anomaly_score` två nya attribut:

| Attribut | Värden |
|---|---|
| `weekly_trend` | `stable` / `slightly_declining` / `declining` / `improving` / `insufficient_data` |
| `trend_reason` | Klartext, t.ex. *"något färre aktiva timmar/dag (7,2 vs 9,1); vaknar 22 min senare än vanligt (08:12 vs 07:50)"* |

Trenden jämför de **senaste 7 dagarna** mot de **föregående 7–21 dagarna** på två mätvärden:
- Genomsnittligt antal timmar per dag med minst en rörelsehändelse
- Genomsnittlig tid för första rörelse

Detta kan upptäcka en gradvis nedgång veckor innan en hälsohändelse, och kan användas i HA-automationer (t.ex. skicka en veckosammanfattning om trenden är `declining`).

---

## Valfri CYD-statusdisplay

Du kan placera en **ESP32-2432S028 ("Cheap Yellow Display")** var som helst i hemmet — på köksbänken, sängbordet eller väggen — och visa en livepanel som familjen ser vid en blick.

```
┌─────────────────────────────────────────────────────────────┐
│  Farmor                          ● Aktiv          17:42     │
├─────────────────────────────────────────────────────────────┤
│  Senast sedd:  Nyss                                          │
│  Senaste rum:  Köket                                         │
│──────────────────────────────────────────────────────────── │
│  Avvikelse: [████████░░░░░░░░░░░░] 42                       │
│  Trend:     Stabil                                           │
│──────────────────────────────────────────────────────────── │
│                  [ Jag mår bra  ✓ ]                          │
└─────────────────────────────────────────────────────────────┘
```

Displayen hämtar data direkt från Home Assistant via ESPHome — inga extra Python-kodändringar eller HA-konfigurationsändringar krävs. Pekknappen längst ner anropar välmåendeknappen om den är konfigurerad.

**Headerfärg:** grön (aktiv) · grå (inaktiv) · röd (larm eller fall)
**Avvikelsestapel:** grön (0–49) · orange (50–79) · röd (80–100)

> **3D-printat case:** färdiga höljedesigner för CYD finns på
> https://makerworld.com/sv/search/models?keyword=cyd%20case

### Vad du behöver

- Ett ESP32-2432S028-kort (~80–120 kr på AliExpress, Amazon, m.m.)
- En USB-kabel (Micro-USB eller USB-C beroende på kortvariant)
- ESPHome (tillgängligt som Home Assistant-tillägg)

### Snabbstart

1. Kopiera `caregiver_display.yaml` till din ESPHome-konfigurationsmapp
2. Redigera tre rader längst upp (person-slug, visningsnamn, välmåendeentitet)
3. Flasha via USB en gång — alla framtida uppdateringar sker trådlöst (OTA)

Se **[DISPLAY_SETUP.md](DISPLAY_SETUP.md)** för den kompletta steg-för-steg-guiden från tomt kort till fungerande display.

---

## Dashboard-kort

Lägg till det egna Lovelace-kortet i valfri dashboard:

```yaml
type: custom:caregiver-card
entity_prefix: farmor        # personnamnet med gemener, mellanslag → understreck
name: Farmor                 # visningsnamn
entry_id: <config_entry_id>  # krävs för åtgärdsknappar
```

För att hitta ditt `config_entry_id`: öppna **Inställningar → Integrationer → Caregiver Mode → Konfigurera** — ID:t är det sista segmentet i webbläsarens URL.

Kortet visar:
- Aktuell status med färgkodning (grön / grå / röd)
- Tid sedan senaste rörelse
- Senaste rum
- Avvikelsespoängens stapel (grön → gul → orange → röd)
- Falllarmbanner med kamerabild och "Åtgärd vidtagen"-knapp
- Avgångslarm-banner

---

## Testtjänster

Alla tjänster kräver `config_entry_id` (se ovan).

| Tjänst | Beskrivning |
|---|---|
| `caregiver_mode.trigger_test_alert` | Simulera ett inaktivitetslarm |
| `caregiver_mode.trigger_test_fall` | Simulera ett falllarm (tar riktig snapshot om kamera är konfigurerad) |
| `caregiver_mode.clear_fall` | Rensa aktivt falllarm och radera snapshot |

Anropa dem via **Utvecklarverktyg → Tjänster**.

---

## Exempel på larmmeddelanden

**Inaktivitetslarm (utan AI):**
> Farmor registrerades senast i Köket kl 08:42. Det är nu 13:15 (onsdag) — 4h 33min utan rörelse.

**Inaktivitetslarm (AI aktiverat):**
> Farmor har inte rört sig sedan 08:42 i Köket. Det är nu halvtiden på eftermiddagen — kanske värt att ringa och höra hur det är?

**Tidig varning (mönsterinlärning):**
> ⚠️ Farmor har inte synts till i morse. Förväntad första rörelse runt 07:27. Avvikelsespoäng: 84/100.

**Falllarm:**
> 🚨 FALL DETEKTERAT – Farmor kan ha fallit. Kameraanalysen visade en person liggande på golvet. Kontrollera omedelbart! (kl 13:07)

**Avgångslarm:**
> 🚶 Farmor har lämnat hemmet — dörren öppnades, ingen rörelse inomhus, telefonen är borta.

---

## Hårdvaruguide och kostnadsuppskattning

Du kan bygga ett komplett övervakningssystem med vanlig konsumentelektronik. Nedan finns tre nivåer från minimal uppsättning till full installation med falldetektering.

> Priser är ungefärliga svenska butikspriser (tidigt 2026). Kontrollera aktuella priser hos Elgiganten, NetOnNet, Kjell & Company, Amazon.se eller AliExpress.

### Vad du behöver för att köra Home Assistant

Om du inte redan har en Home Assistant-server:

| Artikel | Exempel | Ungefärlig kostnad |
|---|---|---|
| Enkortsdator | Raspberry Pi 4 (2 GB) | 600–750 kr |
| Kåpa + fläkt | Officiellt RPi-skal eller Argon ONE | 150–250 kr |
| Strömadapter | Officiell RPi USB-C PSU | 120 kr |
| microSD-kort | 32 GB Class 10 (eller USB SSD) | 80–150 kr |
| **Summa (server)** | | **~950–1 270 kr** |

> En Raspberry Pi 4 med 2 GB RAM kör Home Assistant OS med Caregiver Mode och ett dussintal integrationer utan problem. En begagnad mini-PC (Intel NUC, Dell OptiPlex Micro) är ett alternativ om du vill ha mer headroom.

### Zigbee USB-adapter (krävs för Zigbee-sensorer)

| Artikel | Exempel | Ungefärlig kostnad |
|---|---|---|
| Zigbee-koordinator | SONOFF Zigbee 3.0 USB Dongle Plus | 150–200 kr |

Koppla in den i RPi, installera Zigbee2MQTT- eller ZHA-tillägget i HA — ingen hub eller prenumeration krävs.

---

### Nivå 1 — Grundövervakning (rörelse)

Passar ett litet lgh. Täcker 3 rum.

| Artikel | Antal | Styckpris | Summa |
|---|---|---|---|
| Raspberry Pi 4 + tillbehör | 1 | 1 100 kr | 1 100 kr |
| Zigbee USB-dongle | 1 | 175 kr | 175 kr |
| PIR-rörelsesensor (Zigbee) | 3 | 120 kr | 360 kr |
| **Totalt** | | | **~1 635 kr** |

Rekommenderade rörelsesensorer: SONOFF SNZB-03P (~120 kr), Aqara P1 (~150 kr), IKEA VALLHORN (~100 kr), Philips Hue Motion (~200 kr).

**Vad du får:** inaktivitetslarm + mönsterinlärning. Efter en vecka börjar systemet förutsäga farmors rytm och kan varna dig tidigare än en fast tidsgräns.

---

### Nivå 2 — Standard (+ avgångsdetektion)

Lägger till en dörrkontaktsensor så integrationen kan registrera när personen lämnar hemmet.

| Tillägg | Antal | Styckpris | Summa |
|---|---|---|---|
| Dörrkontaktsensor (Zigbee) | 1 | 100 kr | 100 kr |
| **Nivå 2 totalt** | | | **~1 735 kr** |

Rekommenderade: SONOFF SNZB-04P (~100 kr), Aqara Door and Window Sensor (~130 kr), IKEA PARASOLL (~80 kr).

**Vad du får:** allt i Nivå 1 + notis när personen lämnar/återvänder hem.

---

### Nivå 3 — Full (+ falldetektering)

Lägger till en kamera för AI-driven falldetektering.

| Tillägg | Antal | Styckpris | Summa |
|---|---|---|---|
| IP-kamera (inomhus, 1080p) | 1 | 300–500 kr | 400 kr |
| **Nivå 3 totalt** | | | **~2 135 kr** |

Rekommenderade kameror: TP-Link Tapo C110/C210 (~300–350 kr), Reolink E1 (~250 kr), Aqara G3 (~500 kr).

**Vad du får:** allt i Nivå 1–2 + falldetektering med kamerabild skickad till Telegram/HA.

> **Obs:** Kameran sparar bara ögonblicksbilder lokalt på din HA-server när fall detekteras. Ingen kontinuerlig inspelning, ingen molnuppladdning.

---

### Om du redan har Home Assistant

Behöver du bara komplettera med sensorer:

| Uppsättning | Sensorer som behövs | Ungefärlig kostnad |
|---|---|---|
| Rörelse (3 rum) | 3× PIR + Zigbee-dongle (om ej redan ihopkopplad) | 510–710 kr |
| + Avgångsdetektion | + 1 dörrsensor | 100 kr |
| + Falldetektering | + 1 IP-kamera | 300–500 kr |
| **Full uppgradering** | | **~710–1 310 kr** |

---

### Löpande kostnader

| Post | Kostnad |
|---|---|
| Elektricitet (RPi 4, dygnet runt) | ~40–65 kr / månad |
| Groq API (AI-meddelanden + falldetektering) | **Gratis** (generös gratis-tier) |
| Telegram Bot | **Gratis** |
| Ntfy.sh | **Gratis** (självhostad eller ntfy.sh gratis-plan) |
| HA Cloud (Nabu Casa, valfritt för fjärråtkomst) | 75 kr / månad |

Du kan köra en komplett uppsättning — inklusive AI-genererade larm och falldetektering — till i princip **noll kronor per månad** med gratis-tierna hos Groq och Telegram.

---

## Integritet

- All rörelse- och mönsterdata stannar på din HA-server.
- Kamera-snapshots sparas lokalt och raderas automatiskt när larmet rensas.
- Om AI-meddelanden är aktiverade skickas larmkontext (personnamn, rum, klockslag) till vald AI-leverantör. Bilder skickas inte om du inte använder vision-falldetektering.
- Mönsterdata (rörelseklockslag) lämnar aldrig ditt lokala nätverk.

---

## Integration-ikon (HA 2026.3+)

Från och med Home Assistant 2026.3 kan egna integrationer inkludera egna varumärkesikoner. Placera din ikon i:

```
custom_components/caregiver_mode/brand/icon.png
```

Valfria varianter: `dark_icon.png`, `logo.png`, `logo@2x.png`. Rekommenderad storlek: 256×256 px PNG.

---

## Stöd projektet

Gillar du det här projektet? En kopp kaffe uppskattas ☕

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/wizz666)

---

## Licens

MIT
