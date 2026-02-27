"""Config flow for Caregiver Mode."""
from __future__ import annotations

import re
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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
    DEFAULT_NTFY_SERVER,
    DEFAULT_PERSON_NAME,
    DEFAULT_ACTIVE_START,
    DEFAULT_ACTIVE_END,
    DEFAULT_ALERT_DELAY,
    DEFAULT_ALERT_COOLDOWN,
    AI_PROVIDERS,
    AI_PROVIDER_GROQ,
)

TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _get_motion_sensors(hass: HomeAssistant) -> list[str]:
    """Return all binary_sensor entities with device_class motion or occupancy."""
    result = []
    for state in hass.states.async_all("binary_sensor"):
        dc = state.attributes.get("device_class", "")
        if dc in ("motion", "occupancy"):
            result.append(state.entity_id)
    result.sort()
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
            label = (
                state.attributes.get("friendly_name", s) if state else s
            )
            labels.append(label)
        lines.append(f"• {room_name}: {', '.join(labels)}")
    return "\n".join(lines)


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
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    # ------------------------------------------------------------------
    # Step 2: Room management (menu + sub-steps)
    # ------------------------------------------------------------------

    async def async_step_rooms(self, user_input=None):
        """Room management menu — add rooms until done."""
        menu_options = ["add_room"]
        if self._rooms:
            menu_options.append("done_rooms")

        return self.async_show_menu(
            step_id="rooms",
            menu_options=menu_options,
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
                    {s: s for s in available}
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
                person_name = self._data[CONF_PERSON_NAME]
                await self.async_set_unique_id(
                    f"caregiver_{person_name.lower().replace(' ', '_')}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Caregiver – {person_name}", data=self._data
                )

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


# ---------------------------------------------------------------------------
# Options Flow
# ---------------------------------------------------------------------------


class CaregiverModeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Caregiver Mode."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry
        self._data: dict = {}
        self._rooms: dict[str, list[str]] = {}

    def _merged(self) -> dict:
        """Return merged config: options override data."""
        return {**self._config_entry.data, **self._config_entry.options}

    # ------------------------------------------------------------------
    # Step 1: Basic settings
    # ------------------------------------------------------------------

    async def async_step_init(self, user_input=None):
        """Step 1: Timing and alert thresholds (person_name is locked)."""
        merged = self._merged()
        errors = {}

        if user_input is not None:
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_START, "")):
                errors[CONF_ACTIVE_START] = "invalid_time"
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_END, "")):
                errors[CONF_ACTIVE_END] = "invalid_time"

            if not errors:
                self._data.update(user_input)
                # Pre-populate rooms from existing config
                current_room_map: dict = merged.get(CONF_ROOM_NAMES, {})
                current_sensors: list = merged.get(
                    CONF_MOTION_SENSORS, list(current_room_map.keys())
                )
                self._rooms = _data_to_rooms(current_room_map, current_sensors)
                return await self.async_step_rooms()

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

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    # ------------------------------------------------------------------
    # Step 2: Room management (menu + sub-steps)
    # ------------------------------------------------------------------

    async def async_step_rooms(self, user_input=None):
        """Room management menu."""
        menu_options = ["add_room"]
        if self._rooms:
            menu_options.append("remove_room")
            menu_options.append("done_rooms")

        return self.async_show_menu(
            step_id="rooms",
            menu_options=menu_options,
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
                    {s: s for s in available}
                ),
            }
        )

        return self.async_show_form(
            step_id="add_room", data_schema=schema, errors=errors
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
        """Finalize rooms and proceed to notifications."""
        all_sensors, sensor_room_map = _rooms_to_data(self._rooms)
        self._data[CONF_MOTION_SENSORS] = all_sensors
        self._data[CONF_ROOM_NAMES] = sensor_room_map
        return await self.async_step_notifications()

    # ------------------------------------------------------------------
    # Step 3: Notifications
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
                self._data.update(user_input)
                return self.async_create_entry(title="", data=self._data)

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
