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

# Defaults
DEFAULT_PERSON_NAME = "Farmor"
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

# Sensor unique id suffixes
SUFFIX_STATUS = "status"
SUFFIX_LAST_SEEN = "last_seen"
SUFFIX_LAST_ROOM = "last_room"
SUFFIX_ALERT = "alert"
