"""Config flow for Caregiver Mode."""
from __future__ import annotations

import re
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_PERSON_NAME,
    CONF_ACTIVE_START,
    CONF_ACTIVE_END,
    CONF_ALERT_DELAY,
    CONF_ALERT_COOLDOWN,
    CONF_MOTION_SENSORS,
    CONF_ROOM_NAMES,
    CONF_ROOM_NAME,
    CONF_NOTIFY_PRIMARY,
    CONF_NOTIFY_SECONDARY,
    CONF_AI_ENABLED,
    CONF_AI_PROVIDER,
    CONF_AI_API_KEY,
    CONF_TELEGRAM_BOT_TOKEN,
    CONF_TELEGRAM_CHAT_IDS,
    CONF_NTFY_TOPIC,
    CONF_NTFY_SERVER,
    CONF_DEVICE_TRACKER,
    CONF_EXIT_SENSORS,
    CONF_DEPARTURE_DELAY,
    CONF_CAMERA_ENTITY,
    CONF_VISION_PROVIDER,
    CONF_VISION_API_KEY,
    CONF_OLLAMA_URL,
    CONF_OLLAMA_MODEL,
    CONF_FALL_CONFIRM_COUNT,
    CONF_GROQ_VISION_MODEL,
    CONF_LANGUAGE,
    DEFAULT_NTFY_SERVER,
    DEFAULT_PERSON_NAME,
    DEFAULT_ACTIVE_START,
    DEFAULT_ACTIVE_END,
    DEFAULT_ALERT_DELAY,
    DEFAULT_ALERT_COOLDOWN,
    DEFAULT_DEPARTURE_DELAY,
    DEFAULT_LANGUAGE,
    DEFAULT_OLLAMA_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_GROQ_VISION_MODEL,
    DEFAULT_FALL_CONFIRM_COUNT,
    LANGUAGES,
    AI_PROVIDERS,
    AI_PROVIDER_GROQ,
    VISION_PROVIDERS,
    VISION_PROVIDER_GROQ,
    VISION_PROVIDER_OLLAMA,
    VISION_PROVIDER_ANTHROPIC,
    VISION_PROVIDER_OPENAI,
)

TIME_RE = re.compile(r"^\d{2}:\d{2}$")

CONF_ACTION = "action"


def _get_motion_sensors(hass: HomeAssistant) -> list[str]:
    """Return binary_sensors suitable for activity detection.

    Includes:
      - Any sensor with device_class: motion, occupancy, presence,
        door, opening, window (classified sensors)
      - Unclassified binary_sensors whose friendly name or entity_id
        contains motion/presence/PIR-related keywords
    """
    ALLOWED_CLASSES = {
        "motion", "occupancy", "presence",
        "door", "opening", "window",
    }
    KEYWORDS = {
        "motion", "rörelse", "pir", "presence", "närvaro",
        "occupancy", "detect",
    }
    result = []
    for state in hass.states.async_all("binary_sensor"):
        dc = state.attributes.get("device_class", "")
        if dc in ALLOWED_CLASSES:
            result.append(state.entity_id)
            continue
        if dc == "":
            name = state.attributes.get("friendly_name", state.entity_id).lower()
            eid = state.entity_id.lower()
            if any(kw in name or kw in eid for kw in KEYWORDS):
                result.append(state.entity_id)
    result.sort()
    return result


def _sensor_labels(hass: HomeAssistant, entity_ids: list[str]) -> dict[str, str]:
    """Return {entity_id: 'Friendly Name (device_class)'} for use in multi_select."""
    result = {}
    for eid in entity_ids:
        state = hass.states.get(eid)
        if state:
            name = state.attributes.get("friendly_name", eid)
            dc = state.attributes.get("device_class", "")
            label = f"{name} ({dc})" if dc else name
        else:
            label = eid
        result[eid] = label
    return result


def _get_notify_services(hass: HomeAssistant) -> list[str]:
    """Return all available notify services."""
    services = hass.services.async_services().get("notify", {})
    return sorted(f"notify.{svc}" for svc in services if svc != "notify")


def _rooms_to_data(rooms: dict[str, list[str]]) -> tuple[list[str], dict[str, str]]:
    """Convert rooms dict {room_name: [sensor_ids]} to (all_sensors, sensor_room_map)."""
    all_sensors: list[str] = []
    sensor_room_map: dict[str, str] = {}
    for room_name, sensors in rooms.items():
        for s in sensors:
            all_sensors.append(s)
            sensor_room_map[s] = room_name
    return all_sensors, sensor_room_map


def _data_to_rooms(
    room_map: dict[str, str], sensor_order: list[str]
) -> dict[str, list[str]]:
    """Convert sensor_room_map back to {room_name: [sensor_ids]}, preserving order."""
    rooms: dict[str, list[str]] = {}
    for sensor in sensor_order:
        room = room_map.get(sensor)
        if room:
            rooms.setdefault(room, []).append(sensor)
    return rooms


def _rooms_summary(rooms: dict[str, list[str]], hass: HomeAssistant) -> str:
    """Build a human-readable summary of configured rooms and their sensors."""
    if not rooms:
        return "(inga rum tillagda ännu)"
    lines = []
    for room_name, sensors in rooms.items():
        labels = []
        for s in sensors:
            state = hass.states.get(s)
            label = state.attributes.get("friendly_name", s) if state else s
            labels.append(label)
        lines.append(f"• {room_name}: {', '.join(labels)}")
    return "\n".join(lines)


def _get_exit_sensors(hass: HomeAssistant) -> list[str]:
    """Return door/opening/window binary sensors suitable as exit sensors."""
    result = []
    for state in hass.states.async_all("binary_sensor"):
        dc = state.attributes.get("device_class", "")
        if dc in ("door", "opening", "window"):
            result.append(state.entity_id)
    result.sort()
    return result


def _get_cameras(hass: HomeAssistant) -> dict[str, str]:
    """Return {entity_id: friendly_name} for all camera entities."""
    result = {"": "(Ingen kamera – hoppa över falldetektering)"}
    for state in hass.states.async_all("camera"):
        name = state.attributes.get("friendly_name", state.entity_id)
        result[state.entity_id] = name
    return result


def _get_device_trackers(hass: HomeAssistant) -> dict[str, str]:
    """Return {entity_id: friendly_name} for person and device_tracker entities.

    person.* entities are listed first — they aggregate multiple trackers
    and are the recommended way to track people in HA.
    """
    result = {"": "(Ingen spårning)"}
    # person.* first (aggregated, recommended)
    for state in hass.states.async_all("person"):
        name = state.attributes.get("friendly_name", state.entity_id)
        result[state.entity_id] = f"👤 {name}"
    # raw device_tracker.*
    for state in hass.states.async_all("device_tracker"):
        name = state.attributes.get("friendly_name", state.entity_id)
        result[state.entity_id] = f"📱 {name}"
    return result


def _action_selector(options: list[tuple[str, str]]) -> selector.SelectSelector:
    """Build a dropdown selector from [(value, label), ...] pairs."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=v, label=l)
                for v, l in options
            ],
            mode=selector.SelectSelectorMode.LIST,
        )
    )


# ---------------------------------------------------------------------------
# Config Flow
# ---------------------------------------------------------------------------


class CaregiverModeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Caregiver Mode."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}
        self._rooms: dict[str, list[str]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return CaregiverModeOptionsFlow(config_entry)

    # ------------------------------------------------------------------
    # Step 1: Basic settings
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input=None):
        """Step 1: Person name and timing."""
        errors = {}

        if user_input is not None:
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_START, "")):
                errors[CONF_ACTIVE_START] = "invalid_time"
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_END, "")):
                errors[CONF_ACTIVE_END] = "invalid_time"

            if not errors:
                self._data.update(user_input)
                return await self.async_step_rooms()

        schema = vol.Schema(
            {
                vol.Required(CONF_PERSON_NAME, default=DEFAULT_PERSON_NAME): str,
                vol.Required(CONF_ACTIVE_START, default=DEFAULT_ACTIVE_START): str,
                vol.Required(CONF_ACTIVE_END, default=DEFAULT_ACTIVE_END): str,
                vol.Required(CONF_ALERT_DELAY, default=DEFAULT_ALERT_DELAY): vol.All(
                    int, vol.Range(min=1, max=12)
                ),
                vol.Required(
                    CONF_ALERT_COOLDOWN, default=DEFAULT_ALERT_COOLDOWN
                ): vol.All(int, vol.Range(min=1, max=24)),
                vol.Required(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="auto", label="Auto (follow HA language)"),
                            selector.SelectOptionDict(value="en", label="English"),
                            selector.SelectOptionDict(value="sv", label="Svenska"),
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    # ------------------------------------------------------------------
    # Step 2: Room management — dropdown-based
    # ------------------------------------------------------------------

    async def async_step_rooms(self, user_input=None):
        """Room management: choose action via dropdown."""
        if user_input is not None:
            action = user_input.get(CONF_ACTION)
            if action == "add_room":
                return await self.async_step_add_room()
            if action == "done_rooms":
                return await self.async_step_done_rooms()
            if action == "back":
                return await self.async_step_user()

        options = [("add_room", "Lägg till ett rum")]
        if self._rooms:
            options.append(("done_rooms", "✓ Klar – fortsätt till notifikationer"))
        options.append(("back", "← Tillbaka till grundinställningar"))

        schema = vol.Schema(
            {vol.Required(CONF_ACTION, default="add_room"): _action_selector(options)}
        )

        return self.async_show_form(
            step_id="rooms",
            data_schema=schema,
            description_placeholders={
                "rooms_summary": _rooms_summary(self._rooms, self.hass)
            },
        )

    async def async_step_add_room(self, user_input=None):
        """Add one room with a name and one or more sensors."""
        errors = {}
        all_sensors = _get_motion_sensors(self.hass)
        assigned = {s for sensors in self._rooms.values() for s in sensors}
        available = [s for s in all_sensors if s not in assigned]

        if user_input is not None:
            room_name = user_input.get(CONF_ROOM_NAME, "").strip()
            selected = user_input.get(CONF_MOTION_SENSORS, [])

            if not room_name:
                errors[CONF_ROOM_NAME] = "room_name_required"
            elif room_name in self._rooms:
                errors[CONF_ROOM_NAME] = "room_name_exists"
            if not selected:
                errors[CONF_MOTION_SENSORS] = "no_sensors"

            if not errors:
                self._rooms[room_name] = selected
                return await self.async_step_rooms()

        schema = vol.Schema(
            {
                vol.Required(CONF_ROOM_NAME): str,
                vol.Required(CONF_MOTION_SENSORS): cv.multi_select(
                    _sensor_labels(self.hass, available)
                ),
            }
        )

        return self.async_show_form(
            step_id="add_room", data_schema=schema, errors=errors
        )

    async def async_step_done_rooms(self, user_input=None):
        """Finalize rooms and proceed to notifications."""
        all_sensors, sensor_room_map = _rooms_to_data(self._rooms)
        self._data[CONF_MOTION_SENSORS] = all_sensors
        self._data[CONF_ROOM_NAMES] = sensor_room_map
        return await self.async_step_notifications()

    # ------------------------------------------------------------------
    # Step 3: Notifications
    # ------------------------------------------------------------------

    async def async_step_notifications(self, user_input=None):
        """Step 3: Notification settings."""
        errors = {}
        notify_services = _get_notify_services(self.hass)
        notify_options = {s: s for s in notify_services}

        if user_input is not None:
            primary = user_input.get(CONF_NOTIFY_PRIMARY, "")
            if primary and not primary.startswith("notify."):
                errors[CONF_NOTIFY_PRIMARY] = "invalid_notify"

            secondary = user_input.get(CONF_NOTIFY_SECONDARY, "")
            if secondary and not secondary.startswith("notify."):
                errors[CONF_NOTIFY_SECONDARY] = "invalid_notify"

            telegram_token = user_input.get(CONF_TELEGRAM_BOT_TOKEN, "").strip()
            telegram_chat_ids = user_input.get(CONF_TELEGRAM_CHAT_IDS, "").strip()
            if telegram_token and not telegram_chat_ids:
                errors[CONF_TELEGRAM_CHAT_IDS] = "telegram_chat_id_required"

            ntfy_topic = user_input.get(CONF_NTFY_TOPIC, "").strip()

            ai_enabled = user_input.get(CONF_AI_ENABLED, False)
            ai_key = user_input.get(CONF_AI_API_KEY, "").strip()
            if ai_enabled and not ai_key:
                errors[CONF_AI_API_KEY] = "ai_key_required"

            if not errors:
                if not primary and not telegram_token and not ntfy_topic:
                    errors["base"] = "no_channel_configured"

            if not errors:
                self._data.update(user_input)
                return await self.async_step_departure()

        default_primary = notify_services[0] if notify_services else ""

        schema = vol.Schema(
            {
                vol.Optional(CONF_NOTIFY_PRIMARY, default=default_primary): vol.In(
                    notify_options
                ) if notify_services else str,
                vol.Optional(CONF_NOTIFY_SECONDARY, default=""): str,
                vol.Optional(CONF_TELEGRAM_BOT_TOKEN, default=""): str,
                vol.Optional(CONF_TELEGRAM_CHAT_IDS, default=""): str,
                vol.Optional(CONF_NTFY_TOPIC, default=""): str,
                vol.Optional(CONF_NTFY_SERVER, default=DEFAULT_NTFY_SERVER): str,
                vol.Optional(CONF_AI_ENABLED, default=False): bool,
                vol.Optional(CONF_AI_PROVIDER, default=AI_PROVIDER_GROQ): vol.In(
                    AI_PROVIDERS
                ),
                vol.Optional(CONF_AI_API_KEY, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="notifications", data_schema=schema, errors=errors
        )


    async def async_step_departure(self, user_input=None):
        """Step 4: Optional departure detection (phone + exit door sensors)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_camera()

        exit_sensors = _get_exit_sensors(self.hass)
        trackers = _get_device_trackers(self.hass)

        schema = vol.Schema(
            {
                vol.Optional(CONF_DEVICE_TRACKER, default=""): vol.In(trackers),
                vol.Optional(CONF_EXIT_SENSORS, default=[]): cv.multi_select(
                    _sensor_labels(self.hass, exit_sensors)
                ),
                vol.Optional(
                    CONF_DEPARTURE_DELAY, default=DEFAULT_DEPARTURE_DELAY
                ): vol.All(int, vol.Range(min=1, max=15)),
            }
        )

        return self.async_show_form(step_id="departure", data_schema=schema)

    async def async_step_camera(self, user_input=None):
        """Step 5: Optional camera-based fall detection."""
        errors = {}

        if user_input is not None:
            camera = user_input.get(CONF_CAMERA_ENTITY, "")
            provider = user_input.get(CONF_VISION_PROVIDER, VISION_PROVIDER_GROQ)
            api_key = user_input.get(CONF_VISION_API_KEY, "").strip()

            # Accept empty api_key if existing AI key uses same provider (fallback)
            existing_ai_key = self._data.get(CONF_AI_API_KEY, "")
            existing_ai_provider = self._data.get(CONF_AI_PROVIDER, "")
            has_fallback_key = bool(existing_ai_key and existing_ai_provider == provider)

            if camera and provider != VISION_PROVIDER_OLLAMA and not api_key and not has_fallback_key:
                errors[CONF_VISION_API_KEY] = "vision_key_required"

            if not errors:
                self._data.update(user_input)
                person_name = self._data[CONF_PERSON_NAME]
                await self.async_set_unique_id(
                    f"caregiver_{person_name.lower().replace(' ', '_')}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Caregiver – {person_name}", data=self._data
                )

        cameras = _get_cameras(self.hass)

        schema = vol.Schema(
            {
                vol.Optional(CONF_CAMERA_ENTITY, default=""): vol.In(cameras),
                vol.Optional(
                    CONF_VISION_PROVIDER, default=VISION_PROVIDER_GROQ
                ): _action_selector(
                    [
                        (VISION_PROVIDER_GROQ, "Groq LLaVA (gratis, rekommenderas)"),
                        (VISION_PROVIDER_OLLAMA, "Ollama (lokalt, avancerat)"),
                        (VISION_PROVIDER_ANTHROPIC, "Anthropic Claude (betald)"),
                        (VISION_PROVIDER_OPENAI, "OpenAI GPT-4V (betald)"),
                    ]
                ),
                vol.Optional(CONF_VISION_API_KEY, default=""): str,
                vol.Optional(
                    CONF_GROQ_VISION_MODEL, default=DEFAULT_GROQ_VISION_MODEL
                ): str,
                vol.Optional(CONF_OLLAMA_URL, default=DEFAULT_OLLAMA_URL): str,
                vol.Optional(CONF_OLLAMA_MODEL, default=DEFAULT_OLLAMA_MODEL): str,
                vol.Optional(
                    CONF_FALL_CONFIRM_COUNT, default=DEFAULT_FALL_CONFIRM_COUNT
                ): vol.All(int, vol.Range(min=1, max=5)),
            }
        )

        return self.async_show_form(
            step_id="camera", data_schema=schema, errors=errors
        )


# ---------------------------------------------------------------------------
# Options Flow
# ---------------------------------------------------------------------------


class CaregiverModeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Caregiver Mode."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry
        self._rooms: dict[str, list[str]] = {}
        self._rooms_initialized: bool = False
        self._editing_room: str = ""

    def _merged(self) -> dict:
        """Return merged config: options override data."""
        return {**self._config_entry.data, **self._config_entry.options}

    def _save_options(self, overrides: dict) -> dict:
        """Build new options: full merged config (minus person_name) + overrides."""
        new_options = dict(self._merged())
        new_options.pop(CONF_PERSON_NAME, None)
        new_options.update(overrides)
        return new_options

    def _load_rooms(self) -> None:
        """Load rooms from existing config (called once per flow session)."""
        if self._rooms_initialized:
            return
        merged = self._merged()
        current_room_map: dict = merged.get(CONF_ROOM_NAMES, {})
        current_sensors: list = merged.get(
            CONF_MOTION_SENSORS, list(current_room_map.keys())
        )
        self._rooms = _data_to_rooms(current_room_map, current_sensors)
        self._rooms_initialized = True

    # ------------------------------------------------------------------
    # Top-level: dropdown menu
    # ------------------------------------------------------------------

    async def async_step_init(self, user_input=None):
        """Top-level: choose what to configure."""
        if user_input is not None:
            action = user_input.get(CONF_ACTION)
            if action == "timing":
                return await self.async_step_timing()
            if action == "rooms":
                return await self.async_step_rooms()
            if action == "notifications":
                return await self.async_step_notifications()
            if action == "departure":
                return await self.async_step_departure()
            if action == "camera":
                return await self.async_step_camera()
            if action == "language":
                return await self.async_step_language()

        schema = vol.Schema(
            {
                vol.Required(CONF_ACTION, default="rooms"): _action_selector(
                    [
                        ("timing", "Timing & alert thresholds"),
                        ("rooms", "Manage rooms"),
                        ("notifications", "Notification channels"),
                        ("departure", "Departure detection (phone & door)"),
                        ("camera", "Fall detection (camera & AI)"),
                        ("language", "Notification language"),
                    ]
                )
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    # ------------------------------------------------------------------
    # Timing section
    # ------------------------------------------------------------------

    async def async_step_timing(self, user_input=None):
        """Adjust timing and alert thresholds."""
        merged = self._merged()
        errors = {}

        if user_input is not None:
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_START, "")):
                errors[CONF_ACTIVE_START] = "invalid_time"
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_END, "")):
                errors[CONF_ACTIVE_END] = "invalid_time"

            if not errors:
                return self.async_create_entry(
                    title="", data=self._save_options(user_input)
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ACTIVE_START,
                    default=merged.get(CONF_ACTIVE_START, DEFAULT_ACTIVE_START),
                ): str,
                vol.Required(
                    CONF_ACTIVE_END,
                    default=merged.get(CONF_ACTIVE_END, DEFAULT_ACTIVE_END),
                ): str,
                vol.Required(
                    CONF_ALERT_DELAY,
                    default=merged.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY),
                ): vol.All(int, vol.Range(min=1, max=12)),
                vol.Required(
                    CONF_ALERT_COOLDOWN,
                    default=merged.get(CONF_ALERT_COOLDOWN, DEFAULT_ALERT_COOLDOWN),
                ): vol.All(int, vol.Range(min=1, max=24)),
            }
        )

        return self.async_show_form(
            step_id="timing", data_schema=schema, errors=errors
        )

    # ------------------------------------------------------------------
    # Language section
    # ------------------------------------------------------------------

    async def async_step_language(self, user_input=None):
        """Choose notification language."""
        merged = self._merged()

        if user_input is not None:
            return self.async_create_entry(
                title="", data=self._save_options(user_input)
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LANGUAGE,
                    default=merged.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="auto", label="Auto (follow HA language)"),
                            selector.SelectOptionDict(value="en", label="English"),
                            selector.SelectOptionDict(value="sv", label="Svenska"),
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="language", data_schema=schema)

    # ------------------------------------------------------------------
    # Rooms section — dropdown-based
    # ------------------------------------------------------------------

    async def async_step_rooms(self, user_input=None):
        """Room management: choose action via dropdown."""
        self._load_rooms()

        if user_input is not None:
            action = user_input.get(CONF_ACTION)
            if action == "add_room":
                return await self.async_step_add_room()
            if action == "edit_room":
                return await self.async_step_edit_room()
            if action == "remove_room":
                return await self.async_step_remove_room()
            if action == "done_rooms":
                return await self.async_step_done_rooms()
            if action == "back":
                return await self.async_step_init()

        options = [("add_room", "Lägg till ett rum")]
        if self._rooms:
            options += [
                ("edit_room", "Redigera ett rum (lägg till/ta bort sensorer)"),
                ("remove_room", "Ta bort ett rum"),
                ("done_rooms", "✓ Spara rumändringar"),
            ]
        options.append(("back", "← Tillbaka till huvudmenyn"))

        schema = vol.Schema(
            {vol.Required(CONF_ACTION, default="add_room"): _action_selector(options)}
        )

        return self.async_show_form(
            step_id="rooms",
            data_schema=schema,
            description_placeholders={
                "rooms_summary": _rooms_summary(self._rooms, self.hass)
            },
        )

    async def async_step_add_room(self, user_input=None):
        """Add a room with a name and one or more sensors."""
        errors = {}
        all_sensors = _get_motion_sensors(self.hass)
        assigned = {s for sensors in self._rooms.values() for s in sensors}
        available = [s for s in all_sensors if s not in assigned]

        if user_input is not None:
            room_name = user_input.get(CONF_ROOM_NAME, "").strip()
            selected = user_input.get(CONF_MOTION_SENSORS, [])

            if not room_name:
                errors[CONF_ROOM_NAME] = "room_name_required"
            elif room_name in self._rooms:
                errors[CONF_ROOM_NAME] = "room_name_exists"
            if not selected:
                errors[CONF_MOTION_SENSORS] = "no_sensors"

            if not errors:
                self._rooms[room_name] = selected
                return await self.async_step_rooms()

        schema = vol.Schema(
            {
                vol.Required(CONF_ROOM_NAME): str,
                vol.Required(CONF_MOTION_SENSORS): cv.multi_select(
                    _sensor_labels(self.hass, available)
                ),
            }
        )

        return self.async_show_form(
            step_id="add_room", data_schema=schema, errors=errors
        )

    async def async_step_edit_room(self, user_input=None):
        """Choose which room to edit."""
        errors = {}

        if user_input is not None:
            self._editing_room = user_input.get(CONF_ROOM_NAME, "")
            return await self.async_step_edit_room_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_ROOM_NAME): vol.In(
                    {r: r for r in self._rooms.keys()}
                ),
            }
        )

        return self.async_show_form(
            step_id="edit_room", data_schema=schema, errors=errors
        )

    async def async_step_edit_room_sensors(self, user_input=None):
        """Edit the sensors assigned to the selected room."""
        errors = {}
        room_name = self._editing_room
        all_sensors = _get_motion_sensors(self.hass)
        assigned_to_others = {
            s
            for r, sensors in self._rooms.items()
            if r != room_name
            for s in sensors
        }
        available = [s for s in all_sensors if s not in assigned_to_others]
        current = self._rooms.get(room_name, [])

        if user_input is not None:
            selected = user_input.get(CONF_MOTION_SENSORS, [])
            if not selected:
                errors[CONF_MOTION_SENSORS] = "no_sensors"
            else:
                self._rooms[room_name] = selected
                return await self.async_step_rooms()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MOTION_SENSORS, default=current
                ): cv.multi_select(_sensor_labels(self.hass, available)),
            }
        )

        return self.async_show_form(
            step_id="edit_room_sensors",
            data_schema=schema,
            errors=errors,
            description_placeholders={"room_name": room_name},
        )

    async def async_step_remove_room(self, user_input=None):
        """Remove an existing room."""
        errors = {}

        if user_input is not None:
            room_to_remove = user_input.get(CONF_ROOM_NAME)
            if room_to_remove and room_to_remove in self._rooms:
                del self._rooms[room_to_remove]
            return await self.async_step_rooms()

        schema = vol.Schema(
            {
                vol.Required(CONF_ROOM_NAME): vol.In(
                    {r: r for r in self._rooms.keys()}
                ),
            }
        )

        return self.async_show_form(
            step_id="remove_room", data_schema=schema, errors=errors
        )

    async def async_step_done_rooms(self, user_input=None):
        """Save rooms and exit options flow."""
        all_sensors, sensor_room_map = _rooms_to_data(self._rooms)
        return self.async_create_entry(
            title="",
            data=self._save_options(
                {
                    CONF_MOTION_SENSORS: all_sensors,
                    CONF_ROOM_NAMES: sensor_room_map,
                }
            ),
        )

    # ------------------------------------------------------------------
    # Notifications section
    # ------------------------------------------------------------------

    async def async_step_notifications(self, user_input=None):
        """Notification channels and AI settings."""
        merged = self._merged()
        errors = {}
        notify_services = _get_notify_services(self.hass)
        notify_options = {s: s for s in notify_services}

        if user_input is not None:
            primary = user_input.get(CONF_NOTIFY_PRIMARY, "")
            if primary and not primary.startswith("notify."):
                errors[CONF_NOTIFY_PRIMARY] = "invalid_notify"

            secondary = user_input.get(CONF_NOTIFY_SECONDARY, "")
            if secondary and not secondary.startswith("notify."):
                errors[CONF_NOTIFY_SECONDARY] = "invalid_notify"

            telegram_token = user_input.get(CONF_TELEGRAM_BOT_TOKEN, "").strip()
            telegram_chat_ids = user_input.get(CONF_TELEGRAM_CHAT_IDS, "").strip()
            if telegram_token and not telegram_chat_ids:
                errors[CONF_TELEGRAM_CHAT_IDS] = "telegram_chat_id_required"

            ntfy_topic = user_input.get(CONF_NTFY_TOPIC, "").strip()

            ai_enabled = user_input.get(CONF_AI_ENABLED, False)
            ai_key = user_input.get(CONF_AI_API_KEY, "").strip()
            if ai_enabled and not ai_key:
                errors[CONF_AI_API_KEY] = "ai_key_required"

            if not errors:
                if not primary and not telegram_token and not ntfy_topic:
                    errors["base"] = "no_channel_configured"

            if not errors:
                return self.async_create_entry(
                    title="", data=self._save_options(user_input)
                )

        current_primary = merged.get(
            CONF_NOTIFY_PRIMARY,
            notify_services[0] if notify_services else "",
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NOTIFY_PRIMARY, default=current_primary
                ): vol.In(notify_options) if notify_services else str,
                vol.Optional(
                    CONF_NOTIFY_SECONDARY,
                    default=merged.get(CONF_NOTIFY_SECONDARY, ""),
                ): str,
                vol.Optional(
                    CONF_TELEGRAM_BOT_TOKEN,
                    default=merged.get(CONF_TELEGRAM_BOT_TOKEN, ""),
                ): str,
                vol.Optional(
                    CONF_TELEGRAM_CHAT_IDS,
                    default=merged.get(CONF_TELEGRAM_CHAT_IDS, ""),
                ): str,
                vol.Optional(
                    CONF_NTFY_TOPIC, default=merged.get(CONF_NTFY_TOPIC, "")
                ): str,
                vol.Optional(
                    CONF_NTFY_SERVER,
                    default=merged.get(CONF_NTFY_SERVER, DEFAULT_NTFY_SERVER),
                ): str,
                vol.Optional(
                    CONF_AI_ENABLED, default=merged.get(CONF_AI_ENABLED, False)
                ): bool,
                vol.Optional(
                    CONF_AI_PROVIDER,
                    default=merged.get(CONF_AI_PROVIDER, AI_PROVIDER_GROQ),
                ): vol.In(AI_PROVIDERS),
                vol.Optional(
                    CONF_AI_API_KEY, default=merged.get(CONF_AI_API_KEY, "")
                ): str,
            }
        )

        return self.async_show_form(
            step_id="notifications", data_schema=schema, errors=errors
        )

    # ------------------------------------------------------------------
    # Departure detection section
    # ------------------------------------------------------------------

    async def async_step_departure(self, user_input=None):
        """Configure departure detection: phone tracker + exit door sensors."""
        merged = self._merged()

        if user_input is not None:
            return self.async_create_entry(
                title="", data=self._save_options(user_input)
            )

        exit_sensors = _get_exit_sensors(self.hass)
        trackers = _get_device_trackers(self.hass)
        current_exits = merged.get(CONF_EXIT_SENSORS, [])

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEVICE_TRACKER,
                    default=merged.get(CONF_DEVICE_TRACKER, ""),
                ): vol.In(trackers),
                vol.Optional(
                    CONF_EXIT_SENSORS, default=current_exits
                ): cv.multi_select(_sensor_labels(self.hass, exit_sensors)),
                vol.Optional(
                    CONF_DEPARTURE_DELAY,
                    default=merged.get(CONF_DEPARTURE_DELAY, DEFAULT_DEPARTURE_DELAY),
                ): vol.All(int, vol.Range(min=1, max=15)),
            }
        )

        return self.async_show_form(step_id="departure", data_schema=schema)

    async def async_step_camera(self, user_input=None):
        """Configure camera-based fall detection."""
        merged = self._merged()
        errors = {}

        if user_input is not None:
            camera = user_input.get(CONF_CAMERA_ENTITY, "")
            provider = user_input.get(CONF_VISION_PROVIDER, VISION_PROVIDER_GROQ)
            api_key = user_input.get(CONF_VISION_API_KEY, "").strip()

            # Accept empty api_key if existing AI key uses same provider (fallback)
            existing_ai_key = merged.get(CONF_AI_API_KEY, "")
            existing_ai_provider = merged.get(CONF_AI_PROVIDER, "")
            has_fallback_key = bool(existing_ai_key and existing_ai_provider == provider)

            if camera and provider != VISION_PROVIDER_OLLAMA and not api_key and not has_fallback_key:
                errors[CONF_VISION_API_KEY] = "vision_key_required"

            if not errors:
                return self.async_create_entry(
                    title="", data=self._save_options(user_input)
                )

        cameras = _get_cameras(self.hass)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CAMERA_ENTITY,
                    default=merged.get(CONF_CAMERA_ENTITY, ""),
                ): vol.In(cameras),
                vol.Optional(
                    CONF_VISION_PROVIDER,
                    default=merged.get(CONF_VISION_PROVIDER, VISION_PROVIDER_GROQ),
                ): _action_selector(
                    [
                        (VISION_PROVIDER_GROQ, "Groq LLaVA (gratis, rekommenderas)"),
                        (VISION_PROVIDER_OLLAMA, "Ollama (lokalt, avancerat)"),
                        (VISION_PROVIDER_ANTHROPIC, "Anthropic Claude (betald)"),
                        (VISION_PROVIDER_OPENAI, "OpenAI GPT-4V (betald)"),
                    ]
                ),
                vol.Optional(
                    CONF_VISION_API_KEY,
                    default=merged.get(CONF_VISION_API_KEY, ""),
                ): str,
                vol.Optional(
                    CONF_GROQ_VISION_MODEL,
                    default=merged.get(CONF_GROQ_VISION_MODEL, DEFAULT_GROQ_VISION_MODEL),
                ): str,
                vol.Optional(
                    CONF_OLLAMA_URL,
                    default=merged.get(CONF_OLLAMA_URL, DEFAULT_OLLAMA_URL),
                ): str,
                vol.Optional(
                    CONF_OLLAMA_MODEL,
                    default=merged.get(CONF_OLLAMA_MODEL, DEFAULT_OLLAMA_MODEL),
                ): str,
                vol.Optional(
                    CONF_FALL_CONFIRM_COUNT,
                    default=merged.get(CONF_FALL_CONFIRM_COUNT, DEFAULT_FALL_CONFIRM_COUNT),
                ): vol.All(int, vol.Range(min=1, max=5)),
            }
        )

        return self.async_show_form(
            step_id="camera", data_schema=schema, errors=errors
        )
