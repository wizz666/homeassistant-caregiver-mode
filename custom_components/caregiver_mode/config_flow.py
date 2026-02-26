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
    # Sort for consistent display
    result.sort()
    return result


def _get_notify_services(hass: HomeAssistant) -> list[str]:
    """Return all available notify services."""
    services = hass.services.async_services().get("notify", {})
    return sorted(f"notify.{svc}" for svc in services if svc != "notify")


class CaregiverModeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Caregiver Mode."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        """Step 1: Basic settings."""
        errors = {}

        if user_input is not None:
            # Validate time formats
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_START, "")):
                errors[CONF_ACTIVE_START] = "invalid_time"
            if not TIME_RE.match(user_input.get(CONF_ACTIVE_END, "")):
                errors[CONF_ACTIVE_END] = "invalid_time"

            if not errors:
                self._data.update(user_input)
                return await self.async_step_sensors()

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

    async def async_step_sensors(self, user_input=None):
        """Step 2: Select sensors."""
        errors = {}
        motion_sensors = _get_motion_sensors(self.hass)

        if user_input is not None:
            selected = user_input.get(CONF_MOTION_SENSORS, [])
            if not selected:
                errors[CONF_MOTION_SENSORS] = "no_sensors"
            else:
                # Parse room names: comma-separated list aligned to selected sensors
                raw_rooms = user_input.get(CONF_ROOM_NAMES, "")
                room_list = [r.strip() for r in raw_rooms.split(",") if r.strip()]
                # Pad or trim to match number of sensors
                while len(room_list) < len(selected):
                    room_list.append(f"Rum {len(room_list) + 1}")
                room_list = room_list[: len(selected)]
                # Store as dict: sensor_id -> room_name
                room_map = dict(zip(selected, room_list))
                self._data[CONF_MOTION_SENSORS] = selected
                self._data[CONF_ROOM_NAMES] = room_map
                return await self.async_step_notifications()

        # Build default room name string from sensor friendly names
        default_rooms = ", ".join(
            self.hass.states.get(s).attributes.get("friendly_name", s).replace(
                " Motion", ""
            ).replace(" Occupancy", "")
            for s in motion_sensors
        ) if motion_sensors else ""

        schema = vol.Schema(
            {
                vol.Required(CONF_MOTION_SENSORS): cv.multi_select(
                    {s: s for s in motion_sensors}
                ),
                vol.Optional(CONF_ROOM_NAMES, default=default_rooms): str,
            }
        )

        return self.async_show_form(
            step_id="sensors", data_schema=schema, errors=errors
        )

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

            # At least one channel must be configured
            if not errors:
                if not primary and not telegram_token and not ntfy_topic:
                    errors["base"] = "no_channel_configured"

            if not errors:
                self._data.update(user_input)
                person_name = self._data[CONF_PERSON_NAME]
                # Check for duplicate
                await self.async_set_unique_id(
                    f"caregiver_{person_name.lower().replace(' ', '_')}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Caregiver – {person_name}", data=self._data
                )

        # Default primary to first available notify service
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
