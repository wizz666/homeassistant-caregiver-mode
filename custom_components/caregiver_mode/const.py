"""Constants for Caregiver Mode integration."""

DOMAIN = "caregiver_mode"

# Config keys
CONF_PERSON_NAME = "person_name"
CONF_ACTIVE_START = "active_start"
CONF_ACTIVE_END = "active_end"
CONF_ALERT_DELAY = "alert_delay"
CONF_ALERT_COOLDOWN = "alert_cooldown"
CONF_MOTION_SENSORS = "motion_sensors"
CONF_ROOM_NAMES = "room_names"
CONF_ROOM_NAME = "room_name"
CONF_NOTIFY_PRIMARY = "notify_primary"
CONF_NOTIFY_SECONDARY = "notify_secondary"
CONF_AI_ENABLED = "ai_enabled"
CONF_AI_PROVIDER = "ai_provider"
CONF_AI_API_KEY = "ai_api_key"

# Telegram
CONF_TELEGRAM_BOT_TOKEN = "telegram_bot_token"
CONF_TELEGRAM_CHAT_IDS = "telegram_chat_ids"

# Ntfy.sh
CONF_NTFY_TOPIC = "ntfy_topic"
CONF_NTFY_SERVER = "ntfy_server"
DEFAULT_NTFY_SERVER = "https://ntfy.sh"

# Language
CONF_LANGUAGE = "language"
DEFAULT_LANGUAGE = "auto"
LANGUAGES = ["auto", "en", "sv"]

# Defaults
DEFAULT_PERSON_NAME = "Grandma"
DEFAULT_ACTIVE_START = "07:00"
DEFAULT_ACTIVE_END = "22:00"
DEFAULT_ALERT_DELAY = 4
DEFAULT_ALERT_COOLDOWN = 6

# AI providers
AI_PROVIDER_GROQ = "groq"
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_OPENAI = "openai"
AI_PROVIDERS = [AI_PROVIDER_GROQ, AI_PROVIDER_ANTHROPIC, AI_PROVIDER_OPENAI]

# Departure detection
CONF_DEVICE_TRACKER = "device_tracker"
CONF_EXIT_SENSORS = "exit_sensors"
CONF_DEPARTURE_DELAY = "departure_delay"
DEFAULT_DEPARTURE_DELAY = 5  # minutes to wait after door closes before checking

# Status values
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_ALERT = "alert"
STATUS_UNKNOWN = "unknown"

# Periodic check interval (seconds)
CHECK_INTERVAL = 300

# Vision / Camera (V2.0)
CONF_CAMERA_ENTITY = "camera_entity"
CONF_VISION_PROVIDER = "vision_provider"
CONF_VISION_API_KEY = "vision_api_key"
CONF_OLLAMA_URL = "ollama_url"
CONF_OLLAMA_MODEL = "ollama_model"
CONF_FALL_CONFIRM_COUNT = "fall_confirm_count"

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "moondream"
DEFAULT_GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
DEFAULT_FALL_CONFIRM_COUNT = 2

CONF_GROQ_VISION_MODEL = "groq_vision_model"

FALL_POLL_INTERVAL = 60  # seconds between fall detection snapshots

# Wellness button (V4.0)
CONF_WELLNESS_BUTTON = "wellness_button"

# Escalation chain (V4.0)
CONF_ESCALATION_SERVICES = "escalation_services"
CONF_ESCALATION_DELAY = "escalation_delay"
DEFAULT_ESCALATION_DELAY = 15  # minutes

# Pattern learning (V3.0)
CONF_PATTERN_ENABLED = "pattern_learning_enabled"
CONF_ANOMALY_ALERT_ENABLED = "anomaly_alert_enabled"
CONF_ANOMALY_ALERT_THRESHOLD = "anomaly_alert_threshold"
DEFAULT_PATTERN_ENABLED = True
DEFAULT_ANOMALY_ALERT_ENABLED = False
DEFAULT_ANOMALY_ALERT_THRESHOLD = 75
PATTERN_MIN_DAYS = 7
PATTERN_HISTORY_DAYS = 60
NIGHTLY_JOB_TIME = "02:00:00"

VISION_PROVIDER_GROQ = "groq"
VISION_PROVIDER_OLLAMA = "ollama"
VISION_PROVIDER_ANTHROPIC = "anthropic"
VISION_PROVIDER_OPENAI = "openai"
VISION_PROVIDERS = [
    VISION_PROVIDER_GROQ,
    VISION_PROVIDER_OLLAMA,
    VISION_PROVIDER_ANTHROPIC,
    VISION_PROVIDER_OPENAI,
]

# Sensor unique id suffixes
SUFFIX_STATUS = "status"
SUFFIX_LAST_SEEN = "last_seen"
SUFFIX_LAST_ROOM = "last_room"
SUFFIX_ALERT = "alert"
SUFFIX_FALL = "fall_detected"
SUFFIX_ANOMALY = "anomaly_score"

# Weekday names per language
WEEKDAYS: dict[str, list[str]] = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "sv": ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"],
}

# Notification message templates per language
# Use str.format() with named keys: {name}, {room}, {time}, {now}, {weekday},
# {hours}, {mins}, {minutes}, {start}, {end}
MESSAGES: dict[str, dict] = {
    "en": {
        "inactivity_fallback": (
            "{name} was last seen in {room} at {time}. "
            "It is now {now} ({weekday}) — {hours}h {mins}min without motion."
        ),
        "ai_prompt": (
            "Person: {name}\n"
            "Active hours: {start}–{end}\n"
            "Last motion: {time} in {room}\n"
            "Current time: {now}\n"
            "Day: {weekday}\n"
            "Time since last motion: {hours}h {mins}min\n\n"
            "Write a short, calm message in English informing the family about the situation. "
            "Max 2 sentences. Mention the specific time and room. Avoid alarmism. "
            "Only provide the message text, nothing else."
        ),
        "fall_title": "🚨 FALL DETECTED – {name}",
        "fall_message": (
            "{name} may have fallen. The camera analysis showed a person lying on the floor. "
            "Please check immediately! ({time})"
        ),
        "inactivity_reason": "No motion for {minutes} min (threshold: {hours}h)",
        "inactivity_title": "⚠️ Caregiver – {name}",
        "early_warning_title": "⚠️ Early warning – {name}",
        "early_warning_message": (
            "{name} has not been seen this morning. "
            "Expected first movement around {expected}. "
            "Current anomaly score: {score}/100."
        ),
        "wellness_title": "✅ {name} is OK",
        "wellness_message": (
            "{name} pressed the 'I'm OK' button at {time}. "
            "Everything is fine — no need to worry!"
        ),
        "escalation_title": "🔴 ESCALATION – {name} (no response)",
        "escalation_message": (
            "An alert was sent {delay} min ago with no acknowledgement. "
            "{name} was last seen in {room} at {time}. "
            "This escalation is being sent to additional contacts."
        ),
        "departure": {
            "tracker_left": (
                "📱 {name} has left home",
                "{name}'s phone has left the home network.",
            ),
            "left_confirmed": (
                "🚶 {name} has left home",
                "The door was opened and closed, no indoor motion and the phone is gone.",
            ),
            "left_likely": (
                "🚪 {name} may have left home",
                "The front door was opened and closed but no motion sensors registered activity afterwards.",
            ),
            "forgot_phone": (
                "⚠️ {name} may have left without their phone",
                "The door opened and closed, no indoor motion — but the phone is still home. Did {name} forget it?",
            ),
            "returned_home": (
                "🏠 {name} is back home",
                "{name}'s phone is back on the home network.",
            ),
        },
    },
    "sv": {
        "inactivity_fallback": (
            "{name} registrerades senast i {room} kl {time}. "
            "Det är nu {now} ({weekday}) — {hours}h {mins}min utan rörelse."
        ),
        "ai_prompt": (
            "Person: {name}\n"
            "Normala aktiva timmar: {start}–{end}\n"
            "Senaste registrerade rörelse: {time} i {room}\n"
            "Nuvarande tid: {now}\n"
            "Dag: {weekday}\n"
            "Tid sedan senaste rörelse: {hours}h {mins}min\n\n"
            "Skriv ett kort, lugnt SMS på svenska som informerar familjen om situationen. "
            "Max 2 meningar. Nämn specifik tid och rum. Undvik alarmism. "
            "Ge bara meddelandetexten, inget annat."
        ),
        "fall_title": "🚨 FALL DETEKTERAT – {name}",
        "fall_message": (
            "{name} kan ha fallit. Kameraanalysen visade en person liggande på golvet. "
            "Kontrollera omedelbart! (kl {time})"
        ),
        "inactivity_reason": "Ingen rörelse på {minutes} minuter (gräns {hours} timmar)",
        "inactivity_title": "⚠️ Caregiver – {name}",
        "early_warning_title": "⚠️ Tidig varning – {name}",
        "early_warning_message": (
            "{name} har inte synts till i morse. "
            "Förväntad första rörelse runt {expected}. "
            "Avvikelsespoäng: {score}/100."
        ),
        "wellness_title": "✅ {name} mår bra",
        "wellness_message": (
            "{name} tryckte på 'Jag mår bra'-knappen kl {time}. "
            "Allt är väl — ingen anledning till oro!"
        ),
        "escalation_title": "🔴 ESKALERING – {name} (ingen bekräftelse)",
        "escalation_message": (
            "Larmet skickades för {delay} minuter sedan utan bekräftelse. "
            "{name} registrerades senast i {room} kl {time}. "
            "Detta är en eskalering till ytterligare kontakter."
        ),
        "departure": {
            "tracker_left": (
                "📱 {name} har lämnat hemmet",
                "{name}s telefon har lämnat hemnätverket.",
            ),
            "left_confirmed": (
                "🚶 {name} har lämnat hemmet",
                "Dörren öppnades och stängdes, ingen rörelse inomhus och telefonen är borta.",
            ),
            "left_likely": (
                "🚪 {name} kan ha lämnat hemmet",
                "Ytterdörren öppnades och stängdes men inga rörelsesensorer registrerade rörelse efteråt.",
            ),
            "forgot_phone": (
                "⚠️ {name} kan ha lämnat hemmet utan telefonen",
                "Dörren öppnades och stängdes, ingen rörelse inomhus — men telefonen är kvar. Har {name} glömt den?",
            ),
            "returned_home": (
                "🏠 {name} är hemma igen",
                "{name}s telefon är tillbaka i hemnätverket.",
            ),
        },
    },
}
