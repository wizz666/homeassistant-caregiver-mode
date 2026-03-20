"""Caregiver Mode – AI-assisted motion monitoring for Home Assistant."""
from __future__ import annotations

import asyncio
import base64
import logging
from datetime import date, datetime, timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)

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
    CONF_ACTIVITY_SENSORS,
    CONF_ACTIVITY_THRESHOLD,
    CONF_WEEKLY_SUMMARY_ENABLED,
    CONF_WEEKLY_SUMMARY_DAY,
    CONF_WEEKLY_SUMMARY_HOUR,
    CONF_CALLMEBOT_PHONES,
    CONF_CALLMEBOT_API_KEY,
    CONF_WELLNESS_BUTTON,
    CONF_ESCALATION_SERVICES,
    CONF_ESCALATION_DELAY,
    CONF_PATTERN_ENABLED,
    CONF_ANOMALY_ALERT_ENABLED,
    CONF_ANOMALY_ALERT_THRESHOLD,
    DEFAULT_ACTIVITY_THRESHOLD,
    DEFAULT_WEEKLY_SUMMARY_DAY,
    DEFAULT_WEEKLY_SUMMARY_HOUR,
    DEFAULT_NTFY_SERVER,
    DEFAULT_DEPARTURE_DELAY,
    DEFAULT_ESCALATION_DELAY,
    DEFAULT_LANGUAGE,
    DEFAULT_OLLAMA_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_GROQ_VISION_MODEL,
    DEFAULT_FALL_CONFIRM_COUNT,
    DEFAULT_PATTERN_ENABLED,
    DEFAULT_ANOMALY_ALERT_ENABLED,
    DEFAULT_ANOMALY_ALERT_THRESHOLD,
    CHECK_INTERVAL,
    FALL_POLL_INTERVAL,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_ALERT,
    STATUS_UNKNOWN,
    AI_PROVIDER_GROQ,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OPENAI,
    VISION_PROVIDER_GROQ,
    VISION_PROVIDER_OLLAMA,
    VISION_PROVIDER_ANTHROPIC,
    VISION_PROVIDER_OPENAI,
    WEEKDAYS,
    MESSAGES,
)
from .pattern import CaregiverPatternLearner

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Caregiver Mode from a config entry."""
    coordinator = CaregiverCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Show setup guide if no rooms configured yet (first install)
    if not entry.data.get("rooms"):
        from homeassistant.components.persistent_notification import async_create as pn_create
        person = entry.data.get("person_name", "")
        pn_create(
            hass,
            title=f"Caregiver Mode – {person} installed ✓",
            message=(
                "**Next step: add rooms and sensors**\n\n"
                "Go to **Settings → Integrations → Caregiver Mode** "
                "and press ⚙️ **Configure** to set up:\n\n"
                "- **Rooms** – add rooms with motion sensors\n"
                "- **Notifications** – choose how you receive alerts\n"
                "- **Timing** – set active monitoring hours\n\n"
                "You can change all settings at any time from the same menu."
            ),
            notification_id=f"caregiver_setup_{entry.entry_id}",
        )

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, "trigger_test_fall"):
        async def _handle_test_fall(call) -> None:
            entry_id = call.data.get("config_entry_id")
            coord = hass.data.get(DOMAIN, {}).get(entry_id)
            if coord:
                coord.fall_detected = True
                coord.fall_since = datetime.now().astimezone()
                coord._fall_confirmations = coord.fall_confirm_count
                # Save a real snapshot if camera is configured
                if coord.camera_entity:
                    image_b64, _ = await coord._get_camera_snapshot()
                    if image_b64:
                        await coord._save_fall_snapshot(image_b64)
                coord._notify_entities()
                await coord._send_fall_alert()

        async def _handle_test_alert(call) -> None:
            entry_id = call.data.get("config_entry_id")
            coord = hass.data.get(DOMAIN, {}).get(entry_id)
            if coord:
                coord.alert_active = True
                coord.alert_since = datetime.now().astimezone()
                coord.alert_reason = "Testlarm – manuellt utlöst"
                coord._notify_entities()
                await coord._send_alert()

        async def _handle_clear_fall(call) -> None:
            entry_id = call.data.get("config_entry_id")
            coord = hass.data.get(DOMAIN, {}).get(entry_id)
            if coord:
                coord.fall_detected = False
                coord.fall_since = None
                coord._fall_confirmations = 0
                coord._fall_snapshot_path = ""
                coord.hass.async_add_executor_job(coord._delete_fall_snapshot)
                coord._notify_entities()
                _LOGGER.info("Caregiver [%s]: fall alert cleared via service", coord.person_name)

        hass.services.async_register(DOMAIN, "trigger_test_fall", _handle_test_fall)
        hass.services.async_register(DOMAIN, "trigger_test_alert", _handle_test_alert)
        hass.services.async_register(DOMAIN, "clear_fall", _handle_clear_fall)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: CaregiverCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        await coordinator.async_teardown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


class CaregiverCoordinator:
    """Coordinates motion tracking, alerting, and AI messaging."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._callbacks: list[Callable] = []

        # Load config — options override initial data
        data = {**entry.data, **entry.options}
        self.person_name: str = data[CONF_PERSON_NAME]
        self.active_start: str = data.get(CONF_ACTIVE_START, "07:00")
        self.active_end: str = data.get(CONF_ACTIVE_END, "22:00")
        self.alert_delay_hours: int = data.get(CONF_ALERT_DELAY, 4)
        self.alert_cooldown_hours: int = data.get(CONF_ALERT_COOLDOWN, 6)
        self.sensor_room_map: dict[str, str] = data.get(CONF_ROOM_NAMES, {})
        self.notify_primary: str = data.get(CONF_NOTIFY_PRIMARY, "")
        self.notify_secondary: str = data.get(CONF_NOTIFY_SECONDARY, "")
        self.telegram_bot_token: str = data.get(CONF_TELEGRAM_BOT_TOKEN, "")
        self.telegram_chat_ids: list[str] = [
            c.strip()
            for c in data.get(CONF_TELEGRAM_CHAT_IDS, "").split(",")
            if c.strip()
        ]
        self.ntfy_topic: str = data.get(CONF_NTFY_TOPIC, "")
        self.ntfy_server: str = data.get(CONF_NTFY_SERVER, DEFAULT_NTFY_SERVER)
        self.ai_enabled: bool = data.get(CONF_AI_ENABLED, False)
        self.ai_provider: str = data.get(CONF_AI_PROVIDER, AI_PROVIDER_GROQ)
        self.ai_api_key: str = data.get(CONF_AI_API_KEY, "")

        # Wellness button (V4.0)
        self.wellness_button: str = data.get(CONF_WELLNESS_BUTTON, "")

        # Escalation chain (V4.0)
        self.escalation_services: list[str] = [
            s.strip()
            for s in data.get(CONF_ESCALATION_SERVICES, "").split(",")
            if s.strip()
        ]
        self.escalation_delay_minutes: int = data.get(CONF_ESCALATION_DELAY, DEFAULT_ESCALATION_DELAY)
        self._escalation_cancel: "Callable | None" = None

        # Activity sensors — smart plugs etc. (V5.0)
        self.activity_sensors: list[str] = data.get(CONF_ACTIVITY_SENSORS, [])
        self.activity_threshold: float = float(
            data.get(CONF_ACTIVITY_THRESHOLD, DEFAULT_ACTIVITY_THRESHOLD)
        )

        # Weekly summary (V5.0)
        self.weekly_summary_enabled: bool = data.get(CONF_WEEKLY_SUMMARY_ENABLED, False)
        self.weekly_summary_day: int = int(
            data.get(CONF_WEEKLY_SUMMARY_DAY, DEFAULT_WEEKLY_SUMMARY_DAY)
        )
        self.weekly_summary_hour: int = int(
            data.get(CONF_WEEKLY_SUMMARY_HOUR, DEFAULT_WEEKLY_SUMMARY_HOUR)
        )

        # WhatsApp / Callmebot (V5.0)
        self.callmebot_phones: list[str] = [
            p.strip()
            for p in data.get(CONF_CALLMEBOT_PHONES, "").split(",")
            if p.strip()
        ]
        self.callmebot_api_key: str = data.get(CONF_CALLMEBOT_API_KEY, "")

        # Departure detection config
        self.device_tracker: str = data.get(CONF_DEVICE_TRACKER, "")
        self.exit_sensors: list[str] = data.get(CONF_EXIT_SENSORS, [])
        self.departure_delay_minutes: int = data.get(CONF_DEPARTURE_DELAY, DEFAULT_DEPARTURE_DELAY)

        # Inactivity alert state
        self.last_motion_time: datetime | None = None
        self.last_motion_room: str | None = None
        self.alert_active: bool = False
        self.alert_since: datetime | None = None
        self.alert_reason: str | None = None
        self.alert_ai_message: str | None = None
        self._last_alert_sent: datetime | None = None

        # Departure detection state
        self._door_was_opened: bool = False
        self._door_close_time: datetime | None = None
        self._departure_check_cancel: Callable | None = None
        self.departure_alert_active: bool = False

        # Language
        self.language: str = data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

        # Camera / fall detection config
        self.camera_entity: str = data.get(CONF_CAMERA_ENTITY, "")
        self.vision_provider: str = data.get(CONF_VISION_PROVIDER, VISION_PROVIDER_GROQ)
        self.vision_api_key: str = data.get(CONF_VISION_API_KEY, "")
        self.ollama_url: str = data.get(CONF_OLLAMA_URL, DEFAULT_OLLAMA_URL)
        self.ollama_model: str = data.get(CONF_OLLAMA_MODEL, DEFAULT_OLLAMA_MODEL)
        self.fall_confirm_count: int = data.get(CONF_FALL_CONFIRM_COUNT, DEFAULT_FALL_CONFIRM_COUNT)
        self.groq_vision_model: str = data.get(CONF_GROQ_VISION_MODEL, DEFAULT_GROQ_VISION_MODEL)
        # Fallback: reuse AI API key if same provider and no separate vision key given
        if not self.vision_api_key and data.get(CONF_AI_PROVIDER) == self.vision_provider:
            self.vision_api_key = data.get(CONF_AI_API_KEY, "")

        # Fall detection state
        self.fall_detected: bool = False
        self.fall_since: datetime | None = None
        self._fall_confirmations: int = 0
        self._fall_check_active: bool = False
        self._fall_snapshot_path: str = ""  # /local/caregiver_snapshot_slug.jpg

        # Pattern learning (V3.0)
        self.pattern_enabled: bool = data.get(CONF_PATTERN_ENABLED, DEFAULT_PATTERN_ENABLED)
        self.anomaly_alert_enabled: bool = data.get(CONF_ANOMALY_ALERT_ENABLED, DEFAULT_ANOMALY_ALERT_ENABLED)
        self.anomaly_alert_threshold: int = data.get(CONF_ANOMALY_ALERT_THRESHOLD, DEFAULT_ANOMALY_ALERT_THRESHOLD)
        self.anomaly_score: int = -1
        self.anomaly_reason: str = ""
        self._last_early_warning_sent: datetime | None = None
        # pattern is initialized in async_setup after slug is known
        slug = self.person_name.lower().replace(" ", "_")
        self.pattern: CaregiverPatternLearner = CaregiverPatternLearner(slug, self.hass)

        # Subscriptions
        self._unsub_motion: Callable | None = None
        self._unsub_activity: Callable | None = None
        self._unsub_exit: Callable | None = None
        self._unsub_tracker: Callable | None = None
        self._unsub_wellness: Callable | None = None
        self._unsub_timer: Callable | None = None
        self._unsub_fall_timer: Callable | None = None
        self._unsub_nightly: Callable | None = None
        self._unsub_weekly: Callable | None = None

    # -----------------------------------------------------------------
    # Setup / teardown
    # -----------------------------------------------------------------

    async def async_setup(self) -> None:
        """Subscribe to sensor state changes and start periodic check."""
        # Load persisted pattern data
        if self.pattern_enabled:
            await self.pattern.async_load()

        # Motion sensors
        sensor_ids = list(self.sensor_room_map.keys())
        if sensor_ids:
            self._unsub_motion = async_track_state_change_event(
                self.hass, sensor_ids, self._on_motion_event
            )
            _LOGGER.debug(
                "Caregiver [%s]: tracking %d motion sensors", self.person_name, len(sensor_ids)
            )

        # Activity sensors (smart plugs, switches, etc.)
        if self.activity_sensors:
            self._unsub_activity = async_track_state_change_event(
                self.hass, self.activity_sensors, self._on_activity_event
            )
            _LOGGER.debug(
                "Caregiver [%s]: tracking %d activity sensors",
                self.person_name, len(self.activity_sensors),
            )

        # Wellness / "I'm OK" button
        if self.wellness_button:
            self._unsub_wellness = async_track_state_change_event(
                self.hass, [self.wellness_button], self._on_wellness_event
            )
            _LOGGER.debug(
                "Caregiver [%s]: wellness button tracking %s",
                self.person_name, self.wellness_button,
            )

        # Exit door sensors
        if self.exit_sensors:
            self._unsub_exit = async_track_state_change_event(
                self.hass, self.exit_sensors, self._on_exit_sensor_event
            )
            _LOGGER.debug(
                "Caregiver [%s]: tracking %d exit sensors", self.person_name, len(self.exit_sensors)
            )

        # Device tracker (phone)
        if self.device_tracker:
            self._unsub_tracker = async_track_state_change_event(
                self.hass, [self.device_tracker], self._on_tracker_event
            )
            _LOGGER.debug(
                "Caregiver [%s]: tracking device_tracker %s", self.person_name, self.device_tracker
            )

        self._unsub_timer = async_track_time_interval(
            self.hass,
            self._periodic_check,
            timedelta(seconds=CHECK_INTERVAL),
        )

        # Nightly pattern job at 02:00
        if self.pattern_enabled:
            self._unsub_nightly = async_track_time_change(
                self.hass,
                self._nightly_tick,
                hour=2, minute=0, second=0,
            )
            _LOGGER.debug(
                "Caregiver [%s]: nightly pattern job scheduled at 02:00",
                self.person_name,
            )

        # Weekly summary timer
        if self.weekly_summary_enabled:
            self._unsub_weekly = async_track_time_change(
                self.hass,
                self._weekly_summary_tick,
                hour=self.weekly_summary_hour, minute=0, second=0,
            )
            _LOGGER.debug(
                "Caregiver [%s]: weekly summary scheduled day=%d hour=%02d:00",
                self.person_name, self.weekly_summary_day, self.weekly_summary_hour,
            )

        # Fall detection timer (only if camera configured)
        if self.camera_entity:
            self._unsub_fall_timer = async_track_time_interval(
                self.hass,
                self._fall_check_tick,
                timedelta(seconds=FALL_POLL_INTERVAL),
            )
            _LOGGER.debug(
                "Caregiver [%s]: fall detection enabled via %s (provider: %s)",
                self.person_name, self.camera_entity, self.vision_provider,
            )

    async def async_teardown(self) -> None:
        """Remove subscriptions."""
        for unsub in [
            self._unsub_motion,
            self._unsub_activity,
            self._unsub_exit,
            self._unsub_tracker,
            self._unsub_wellness,
            self._unsub_timer,
            self._unsub_fall_timer,
            self._unsub_nightly,
            self._unsub_weekly,
        ]:
            if unsub:
                unsub()
        if self._departure_check_cancel:
            self._departure_check_cancel()
        if self._escalation_cancel:
            self._escalation_cancel()

    # -----------------------------------------------------------------
    # Callbacks for entities
    # -----------------------------------------------------------------

    def register_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    def unregister_callback(self, cb: Callable) -> None:
        try:
            self._callbacks.remove(cb)
        except ValueError:
            pass

    def _notify_entities(self) -> None:
        for cb in list(self._callbacks):
            cb()

    # -----------------------------------------------------------------
    # Status property
    # -----------------------------------------------------------------

    @property
    def status(self) -> str:
        if self.alert_active:
            return STATUS_ALERT
        if self.last_motion_time is None:
            return STATUS_UNKNOWN
        if self._within_active_hours():
            return STATUS_ACTIVE
        return STATUS_INACTIVE

    @property
    def minutes_since_motion(self) -> int | None:
        if self.last_motion_time is None:
            return None
        delta = datetime.now().astimezone() - self.last_motion_time
        return int(delta.total_seconds() / 60)

    # -----------------------------------------------------------------
    # Motion event handler
    # -----------------------------------------------------------------

    @callback
    def _on_motion_event(self, event: Event) -> None:
        """Handle state change from a motion sensor."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        if new_state.state not in ("on", "detected"):
            return

        entity_id = event.data.get("entity_id", "")
        room = self.sensor_room_map.get(entity_id, entity_id)

        _LOGGER.debug("Caregiver [%s]: motion in %s", self.person_name, room)

        now_ts = datetime.now().astimezone()
        self.last_motion_time = now_ts
        self.last_motion_room = room

        # Pattern learning
        if self.pattern_enabled:
            self.pattern.record_motion(now_ts, room)

        if self.alert_active:
            _LOGGER.info(
                "Caregiver [%s]: motion detected — clearing inactivity alert", self.person_name
            )
            self.alert_active = False
            self.alert_since = None
            self.alert_reason = None
            self.alert_ai_message = None
            # Cancel any pending escalation
            if self._escalation_cancel:
                self._escalation_cancel()
                self._escalation_cancel = None

        if self.fall_detected:
            _LOGGER.info(
                "Caregiver [%s]: motion detected — clearing fall alert", self.person_name
            )
            self.fall_detected = False
            self.fall_since = None
            self._fall_confirmations = 0
            self._fall_snapshot_path = ""
            self.hass.async_add_executor_job(self._delete_fall_snapshot)

        self._notify_entities()

    # -----------------------------------------------------------------
    # Activity sensor handler (smart plug / switch / power sensor)
    # -----------------------------------------------------------------

    @callback
    def _on_activity_event(self, event: Event) -> None:
        """Handle state change from an activity sensor (smart plug, kettle, etc.)."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        state_val = new_state.state
        entity_id = event.data.get("entity_id", "")

        # Determine if this state counts as "activity"
        is_active = False
        if state_val in ("on", "active", "detected", "open"):
            is_active = True
        else:
            try:
                power = float(state_val)
                if power >= self.activity_threshold:
                    is_active = True
            except (ValueError, TypeError):
                pass

        if not is_active:
            return

        # Use the entity's friendly_name as the "room/activity" label
        ha_state = self.hass.states.get(entity_id)
        activity_name = (
            ha_state.attributes.get("friendly_name", entity_id)
            if ha_state else entity_id
        )

        now_ts = datetime.now().astimezone()
        _LOGGER.debug(
            "Caregiver [%s]: activity from %s (state=%s)",
            self.person_name, activity_name, state_val,
        )

        self.last_motion_time = now_ts
        self.last_motion_room = activity_name

        if self.pattern_enabled:
            self.pattern.record_motion(now_ts, activity_name)

        if self.alert_active:
            _LOGGER.info(
                "Caregiver [%s]: activity from %s — clearing inactivity alert",
                self.person_name, activity_name,
            )
            self.alert_active = False
            self.alert_since = None
            self.alert_reason = None
            self.alert_ai_message = None
            if self._escalation_cancel:
                self._escalation_cancel()
                self._escalation_cancel = None

        self._notify_entities()

    # -----------------------------------------------------------------
    # Wellness button handler ("I'm OK")
    # -----------------------------------------------------------------

    @callback
    def _on_wellness_event(self, event: Event) -> None:
        """Handle state change from the wellness / 'I'm OK' button."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return

        # Ignore non-meaningful states (unavailable, unknown, off, empty)
        IGNORE = {"off", "unavailable", "unknown", ""}
        if new_state.state.lower() in IGNORE:
            return
        # Also ignore if state didn't actually change
        if old_state and new_state.state == old_state.state:
            return

        now_ts = datetime.now().astimezone()
        _LOGGER.info(
            "Caregiver [%s]: wellness button pressed (state=%s)",
            self.person_name, new_state.state,
        )

        # Count as a sign of life
        self.last_motion_time = now_ts

        # Clear any active inactivity alert
        if self.alert_active:
            self.alert_active = False
            self.alert_since = None
            self.alert_reason = None
            self.alert_ai_message = None
            if self._escalation_cancel:
                self._escalation_cancel()
                self._escalation_cancel = None

        self._notify_entities()
        self.hass.async_create_task(self._send_wellness_notification(now_ts))

    async def _send_wellness_notification(self, ts: datetime) -> None:
        """Send 'I'm OK' notification via all configured channels."""
        name = self.person_name
        time_str = ts.strftime("%H:%M")
        title = self._msg("wellness_title", name=name)
        message = self._msg("wellness_message", name=name, time=time_str)

        tasks = []
        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(self._send_ha_notify(svc_full, title, message))
        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))
        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))
        if self.callmebot_phones:
            for phone in self.callmebot_phones:
                tasks.append(self._send_whatsapp(phone, title, message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Caregiver [%s]: wellness notification error: %s",
                        self.person_name, result,
                    )
        _LOGGER.info("Caregiver [%s]: wellness notification sent", self.person_name)

    # -----------------------------------------------------------------
    # Exit sensor handler (departure detection — door open/close)
    # -----------------------------------------------------------------

    @callback
    def _on_exit_sensor_event(self, event: Event) -> None:
        """Handle exit door sensor state change."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        state_val = new_state.state

        if state_val in ("on", "open"):
            # Door opened
            self._door_was_opened = True
            _LOGGER.debug("Caregiver [%s]: exit door opened", self.person_name)

        elif state_val in ("off", "closed") and self._door_was_opened:
            # Door closed after having been opened
            self._door_was_opened = False
            self._door_close_time = datetime.now().astimezone()
            _LOGGER.debug(
                "Caregiver [%s]: exit door closed — scheduling departure check in %d min",
                self.person_name, self.departure_delay_minutes,
            )

            # Cancel any pending check
            if self._departure_check_cancel:
                self._departure_check_cancel()
                self._departure_check_cancel = None

            # Schedule departure check after delay
            self._departure_check_cancel = async_call_later(
                self.hass,
                self.departure_delay_minutes * 60,
                self._check_departure,
            )

    # -----------------------------------------------------------------
    # Device tracker handler (phone leaves / returns home)
    # -----------------------------------------------------------------

    @callback
    def _on_tracker_event(self, event: Event) -> None:
        """Handle device tracker (phone) state change."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or old_state is None:
            return

        old_val = old_state.state
        new_val = new_state.state

        AWAY = {"not_home", "away"}
        HOME = {"home"}
        IGNORE = {"unavailable", "unknown"}

        # Phone just left home → Scenario A
        if old_val in HOME and new_val in AWAY:
            _LOGGER.info("Caregiver [%s]: device tracker left home", self.person_name)
            if self._within_active_hours():
                self.hass.async_create_task(
                    self._send_departure_notification("tracker_left")
                )

        # Phone returned home → clear departure alert
        elif old_val in AWAY and new_val in HOME:
            _LOGGER.info("Caregiver [%s]: device tracker returned home", self.person_name)
            if self.departure_alert_active:
                self.departure_alert_active = False
                self._notify_entities()
                self.hass.async_create_task(
                    self._send_departure_notification("returned_home")
                )

    # -----------------------------------------------------------------
    # Departure check (called after door close delay)
    # -----------------------------------------------------------------

    async def _check_departure(self, _now=None) -> None:
        """Check if person has left based on door event + motion + tracker."""
        self._departure_check_cancel = None

        if self._door_close_time is None:
            return

        # Was there motion AFTER the door closed?
        motion_since_door = (
            self.last_motion_time is not None
            and self.last_motion_time > self._door_close_time
        )

        if motion_since_door:
            _LOGGER.debug(
                "Caregiver [%s]: motion detected after door close — person still home",
                self.person_name,
            )
            return

        # No motion since door closed — correlate with device tracker
        if self.device_tracker:
            tracker_state = self.hass.states.get(self.device_tracker)
            if tracker_state:
                if tracker_state.state == "home":
                    # Scenario C: door + no motion + phone still home → forgot phone
                    _LOGGER.warning(
                        "Caregiver [%s]: likely left but tracker still home (forgot phone?)",
                        self.person_name,
                    )
                    await self._send_departure_notification("forgot_phone")
                else:
                    # Scenario A+B confirmed: door + no motion + tracker away
                    _LOGGER.warning(
                        "Caregiver [%s]: departed (door + no motion + tracker away)",
                        self.person_name,
                    )
                    await self._send_departure_notification("left_confirmed")
                return

        # Scenario B: no tracker, just door + no motion
        _LOGGER.warning(
            "Caregiver [%s]: possibly departed (door closed, no motion since)",
            self.person_name,
        )
        await self._send_departure_notification("left_likely")

    # -----------------------------------------------------------------
    # Departure notification
    # -----------------------------------------------------------------

    async def _send_departure_notification(self, scenario: str) -> None:
        """Send departure-related notification."""
        name = self.person_name
        dep = MESSAGES.get(self._get_lang(), MESSAGES["en"]).get("departure", {})

        def _dep(key: str) -> tuple[str, str]:
            tmpl = dep.get(key, (f"Caregiver – {name}", key))
            return tmpl[0].format(name=name), tmpl[1].format(name=name)

        title, message = _dep(scenario) if scenario in dep else (f"Caregiver – {name}", scenario)

        if scenario != "returned_home":
            self.departure_alert_active = True
        self._notify_entities()

        tasks = []
        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(self._send_ha_notify(svc_full, title, message))
        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))
        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))
        if self.callmebot_phones:
            for phone in self.callmebot_phones:
                tasks.append(self._send_whatsapp(phone, title, message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Caregiver [%s]: departure notification error: %s",
                        self.person_name, result,
                    )

    # -----------------------------------------------------------------
    # Fall detection (camera + vision AI)
    # -----------------------------------------------------------------

    @callback
    def _fall_check_tick(self, now=None) -> None:
        """Periodic fall detection tick — skips if conditions not met."""
        if not self._within_active_hours():
            return
        if self.fall_detected:
            return  # Already alarmed; cleared by motion event
        if self.departure_alert_active:
            return  # Person likely not home
        self.hass.async_create_task(self._do_fall_check())

    async def _do_fall_check(self) -> None:
        """Take a snapshot and run vision analysis for fall detection."""
        if self._fall_check_active:
            return  # Previous check still running
        self._fall_check_active = True
        try:
            image_b64, content_type = await self._get_camera_snapshot()
            if not image_b64:
                return

            fell = await self._analyze_for_fall(image_b64, content_type)

            if fell:
                self._fall_confirmations += 1
                _LOGGER.warning(
                    "Caregiver [%s]: fall candidate (confirmation %d/%d)",
                    self.person_name, self._fall_confirmations, self.fall_confirm_count,
                )
                if self._fall_confirmations >= self.fall_confirm_count and not self.fall_detected:
                    self.fall_detected = True
                    self.fall_since = datetime.now().astimezone()
                    await self._save_fall_snapshot(image_b64)
                    self._notify_entities()
                    await self._send_fall_alert()
            else:
                if not self.fall_detected:
                    self._fall_confirmations = 0
        except Exception as exc:
            _LOGGER.error("Caregiver [%s]: fall check error: %s", self.person_name, exc)
        finally:
            self._fall_check_active = False

    async def _get_camera_snapshot(self) -> tuple[str, str]:
        """Return (base64_image, content_type) from the configured camera."""
        try:
            from homeassistant.components.camera import async_get_image
            image = await async_get_image(self.hass, self.camera_entity, timeout=15)
            b64 = base64.b64encode(image.content).decode("utf-8")
            ct = image.content_type or "image/jpeg"
            return b64, ct
        except Exception as exc:
            _LOGGER.error(
                "Caregiver [%s]: camera snapshot failed (%s): %s",
                self.person_name, self.camera_entity, exc,
            )
            return "", ""

    async def _save_fall_snapshot(self, image_b64: str) -> None:
        """Save fall snapshot to www folder (single file, always overwritten)."""
        import os
        slug = self.person_name.lower().replace(" ", "_")
        filename = f"caregiver_snapshot_{slug}.jpg"
        filepath = f"/config/www/{filename}"
        try:
            image_bytes = base64.b64decode(image_b64)
            await self.hass.async_add_executor_job(
                lambda: open(filepath, "wb").write(image_bytes)
            )
            self._fall_snapshot_path = f"/local/{filename}"
            _LOGGER.debug("Caregiver [%s]: snapshot saved to %s", self.person_name, filepath)
        except Exception as exc:
            _LOGGER.error("Caregiver [%s]: failed to save snapshot: %s", self.person_name, exc)

    def _delete_fall_snapshot(self) -> None:
        """Delete fall snapshot file from www folder."""
        import os
        slug = self.person_name.lower().replace(" ", "_")
        filepath = f"/config/www/caregiver_snapshot_{slug}.jpg"
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                _LOGGER.debug("Caregiver [%s]: snapshot deleted", self.person_name)
        except Exception as exc:
            _LOGGER.error("Caregiver [%s]: failed to delete snapshot: %s", self.person_name, exc)

    async def _analyze_for_fall(self, image_b64: str, content_type: str) -> bool:
        """Call configured vision provider and return True if fall detected."""
        question = (
            "Is there a person lying on the floor or in a position that indicates a fall? "
            "Answer only YES or NO."
        )
        try:
            if self.vision_provider == VISION_PROVIDER_GROQ:
                answer = await self._vision_groq(image_b64, content_type, question)
            elif self.vision_provider == VISION_PROVIDER_OLLAMA:
                answer = await self._vision_ollama(image_b64, question)
            elif self.vision_provider == VISION_PROVIDER_ANTHROPIC:
                answer = await self._vision_anthropic(image_b64, content_type, question)
            elif self.vision_provider == VISION_PROVIDER_OPENAI:
                answer = await self._vision_openai(image_b64, content_type, question)
            else:
                return False

            _LOGGER.debug(
                "Caregiver [%s]: vision answer: %s", self.person_name, answer[:80]
            )
            return "YES" in answer.upper()
        except Exception as exc:
            _LOGGER.error("Caregiver [%s]: vision API error: %s", self.person_name, exc)
            return False

    async def _vision_groq(self, image_b64: str, content_type: str, question: str) -> str:
        import aiohttp
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.vision_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.groq_vision_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_b64}"}},
                    {"type": "text", "text": question},
                ],
            }],
            "max_tokens": 10,
            "temperature": 0.0,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                _LOGGER.error("Groq vision error %d: %s", resp.status, await resp.text())
        return ""

    async def _vision_ollama(self, image_b64: str, question: str) -> str:
        import aiohttp
        url = f"{self.ollama_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.ollama_model,
            "prompt": question,
            "images": [image_b64],
            "stream": False,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "").strip()
                _LOGGER.error("Ollama vision error %d: %s", resp.status, await resp.text())
        return ""

    async def _vision_anthropic(self, image_b64: str, content_type: str, question: str) -> str:
        import aiohttp
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.vision_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        safe_ct = content_type if content_type in (
            "image/jpeg", "image/png", "image/gif", "image/webp"
        ) else "image/jpeg"
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 10,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": safe_ct, "data": image_b64}},
                    {"type": "text", "text": question},
                ],
            }],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"].strip()
                _LOGGER.error("Anthropic vision error %d: %s", resp.status, await resp.text())
        return ""

    async def _vision_openai(self, image_b64: str, content_type: str, question: str) -> str:
        import aiohttp
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.vision_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_b64}"}},
                    {"type": "text", "text": question},
                ],
            }],
            "max_tokens": 10,
            "temperature": 0.0,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                _LOGGER.error("OpenAI vision error %d: %s", resp.status, await resp.text())
        return ""

    async def _send_fall_alert(self) -> None:
        """Send fall detection notification via all configured channels, with camera image."""
        name = self.person_name
        now_str = datetime.now().astimezone().strftime("%H:%M")
        title = self._msg("fall_title", name=name)
        message = self._msg("fall_message", name=name, time=now_str)

        # Get fresh snapshot for Telegram (if camera configured)
        image_b64, image_ct = "", ""
        if self.camera_entity:
            image_b64, image_ct = await self._get_camera_snapshot()

        tasks = []
        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(
                    self._send_ha_notify_fall(svc_full, title, message)
                )
        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                if image_b64:
                    tasks.append(
                        self._send_telegram_photo(chat_id, title, message, image_b64)
                    )
                else:
                    tasks.append(self._send_telegram(chat_id, title, message))
        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))
        if self.callmebot_phones:
            for phone in self.callmebot_phones:
                tasks.append(self._send_whatsapp(phone, title, message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Caregiver [%s]: fall alert error: %s", self.person_name, result
                    )

    async def _send_ha_notify_fall(self, svc_full: str, title: str, message: str) -> None:
        """Send fall alert via HA notify with camera image and tap URL."""
        parts = svc_full.split(".", 1)
        if len(parts) != 2:
            return
        domain, service = parts
        payload: dict = {"title": title, "message": message}
        if self.camera_entity:
            payload["data"] = {
                "image": f"/api/camera_proxy/{self.camera_entity}",
                "url": "/caregiver-dashboard/oversikt",
            }
        else:
            payload["data"] = {"url": "/caregiver-dashboard/oversikt"}
        await self.hass.services.async_call(
            domain, service, payload, blocking=False
        )
        _LOGGER.info("Caregiver [%s]: fall notify sent via %s", self.person_name, svc_full)

    async def _send_telegram_photo(
        self, chat_id: str, title: str, message: str, image_b64: str
    ) -> None:
        """Send fall alert to Telegram as a photo with caption."""
        import aiohttp
        import base64 as _b64
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
        image_bytes = _b64.b64decode(image_b64)
        caption = f"*{title}*\n{message}"
        form = aiohttp.FormData()
        form.add_field("chat_id", chat_id)
        form.add_field("caption", caption)
        form.add_field("parse_mode", "Markdown")
        form.add_field(
            "photo",
            image_bytes,
            filename="snapshot.jpg",
            content_type="image/jpeg",
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, data=form, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info(
                        "Caregiver [%s]: Telegram photo sent to %s",
                        self.person_name, chat_id,
                    )
                else:
                    body = await resp.text()
                    _LOGGER.error(
                        "Caregiver [%s]: Telegram photo error %d: %s — falling back to text",
                        self.person_name, resp.status, body,
                    )
                    await self._send_telegram(chat_id, title, message)

    # -----------------------------------------------------------------
    # Periodic inactivity check
    # -----------------------------------------------------------------

    @callback
    def _periodic_check(self, now=None) -> None:
        """Run every CHECK_INTERVAL seconds."""
        if not self._within_active_hours():
            if self.alert_active:
                self.alert_active = False
                self._notify_entities()
            return

        # Update anomaly score
        if self.pattern_enabled:
            check_now = now if now is not None else datetime.now().astimezone()
            score, reason = self.pattern.get_anomaly_score(check_now, self.active_start)
            score_changed = (score != self.anomaly_score or reason != self.anomaly_reason)
            self.anomaly_score = score
            self.anomaly_reason = reason
            if score_changed:
                self._notify_entities()

            # Early warning (only if anomaly alert enabled and no active inactivity alert)
            if (
                self.anomaly_alert_enabled
                and score >= self.anomaly_alert_threshold
                and not self.alert_active
            ):
                elapsed_s = (
                    (datetime.now().astimezone() - self._last_early_warning_sent).total_seconds()
                    if self._last_early_warning_sent is not None
                    else float("inf")
                )
                if elapsed_s > 3 * 3600:
                    self._last_early_warning_sent = datetime.now().astimezone()
                    self.hass.async_create_task(self._send_early_warning())

        if self.last_motion_time is None:
            return

        minutes = self.minutes_since_motion
        if minutes is None:
            return

        threshold_minutes = self.alert_delay_hours * 60

        if minutes >= threshold_minutes:
            if not self.alert_active:
                self.alert_active = True
                self.alert_since = datetime.now().astimezone()
                self.alert_reason = self._msg(
                    "inactivity_reason",
                    minutes=minutes,
                    hours=self.alert_delay_hours,
                )
                _LOGGER.warning(
                    "Caregiver [%s]: ALERT — %s", self.person_name, self.alert_reason
                )
                self._notify_entities()
                self.hass.async_create_task(self._send_alert())
            else:
                if self._last_alert_sent is not None:
                    elapsed = datetime.now().astimezone() - self._last_alert_sent
                    if elapsed >= timedelta(hours=self.alert_cooldown_hours):
                        self.hass.async_create_task(self._send_alert())

    # -----------------------------------------------------------------
    # Nightly pattern job (02:00)
    # -----------------------------------------------------------------

    @callback
    def _nightly_tick(self, now=None) -> None:
        """Called at 02:00 — schedule nightly pattern finalization."""
        self.hass.async_create_task(self._nightly_job())

    async def _nightly_job(self) -> None:
        """Finalize yesterday's data, recompute model, persist."""
        if not self.pattern_enabled:
            return
        yesterday = (datetime.now() - timedelta(days=1)).date()
        self.pattern.close_day(yesterday)
        self.pattern.compute_model()
        await self.pattern.async_save()
        self._notify_entities()
        _LOGGER.info(
            "Caregiver [%s]: nightly pattern update complete (%d days learned)",
            self.person_name, self.pattern.days_learned,
        )

    # -----------------------------------------------------------------
    # Early warning notification
    # -----------------------------------------------------------------

    async def _send_early_warning(self) -> None:
        """Send early warning via all configured channels."""
        name = self.person_name
        expected = self.pattern.expected_first_motion_today or "—"
        score = self.anomaly_score
        title = self._msg("early_warning_title", name=name)
        message = self._msg(
            "early_warning_message", name=name, expected=expected, score=score
        )
        tasks = []
        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(self._send_ha_notify(svc_full, title, message))
        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))
        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))
        if self.callmebot_phones:
            for phone in self.callmebot_phones:
                tasks.append(self._send_whatsapp(phone, title, message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Caregiver [%s]: early warning error: %s", self.person_name, result
                    )
        _LOGGER.info(
            "Caregiver [%s]: early warning sent (score=%d)", self.person_name, score
        )

    # -----------------------------------------------------------------
    # Weekly summary (V5.0)
    # -----------------------------------------------------------------

    @callback
    def _weekly_summary_tick(self, now=None) -> None:
        """Called every day at weekly_summary_hour — only fires on the configured weekday."""
        check = now if now is not None else datetime.now().astimezone()
        if check.weekday() != self.weekly_summary_day:
            return
        self.hass.async_create_task(self._send_weekly_summary())

    async def _send_weekly_summary(self) -> None:
        """Build and dispatch the weekly activity summary to all channels."""
        name = self.person_name

        # Gather stats from pattern learner
        stats: dict = {}
        trend_label = "—"
        avg_wake = "—"
        if self.pattern_enabled:
            stats = self.pattern.get_week_stats()
            trend, _ = self.pattern.get_weekly_trend()
            lang = self._get_lang()
            trend_labels_en = {
                "stable": "stable", "slightly_declining": "slightly declining",
                "declining": "declining", "improving": "improving",
                "slightly_improving": "slightly improving", "insufficient_data": "insufficient data",
            }
            trend_labels_sv = {
                "stable": "stabil", "slightly_declining": "svagt avtagande",
                "declining": "avtagande", "improving": "förbättrad",
                "slightly_improving": "svagt förbättrad", "insufficient_data": "för lite data",
            }
            trend_map = trend_labels_sv if lang == "sv" else trend_labels_en
            trend_label = trend_map.get(trend, trend)
            avg_fm = stats.get("avg_first_motion")
            if avg_fm is not None:
                h = int(avg_fm) // 60
                m = int(avg_fm) % 60
                avg_wake = f"{h:02d}:{m:02d}"

        active_days = stats.get("active_days", "?")
        total_days = stats.get("total_days", 7)

        title = self._msg("weekly_summary_title", name=name)
        message = self._msg(
            "weekly_summary_message",
            name=name,
            active_days=active_days,
            total_days=total_days,
            avg_wake=avg_wake,
            trend=trend_label,
        )

        tasks = []
        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(self._send_ha_notify(svc_full, title, message))
        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))
        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))
        if self.callmebot_phones:
            for phone in self.callmebot_phones:
                tasks.append(self._send_whatsapp(phone, title, message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Caregiver [%s]: weekly summary error: %s", self.person_name, result
                    )
        _LOGGER.info("Caregiver [%s]: weekly summary sent", self.person_name)

    # -----------------------------------------------------------------
    # Inactivity alert sending
    # -----------------------------------------------------------------

    async def _send_alert(self) -> None:
        """Generate AI message (if enabled) and push notifications via all channels."""
        message = await self._generate_message()
        self.alert_ai_message = message
        self._last_alert_sent = datetime.now().astimezone()
        self._notify_entities()

        title = self._msg("inactivity_title", name=self.person_name)
        tasks = []

        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(self._send_ha_notify(svc_full, title, message))

        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))

        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))

        if self.callmebot_phones:
            for phone in self.callmebot_phones:
                tasks.append(self._send_whatsapp(phone, title, message))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.error(
                    "Caregiver [%s]: notification channel error: %s",
                    self.person_name, result,
                )

        # Schedule escalation if configured (only on first alert, not repeats)
        if self.escalation_services and not self._escalation_cancel:
            self._escalation_cancel = async_call_later(
                self.hass,
                self.escalation_delay_minutes * 60,
                self._escalation_tick,
            )
            _LOGGER.info(
                "Caregiver [%s]: escalation scheduled in %d min",
                self.person_name, self.escalation_delay_minutes,
            )

    @callback
    def _escalation_tick(self, _now=None) -> None:
        """Escalation timer fired — send escalation if alert is still active."""
        self._escalation_cancel = None
        if self.alert_active:
            self.hass.async_create_task(self._send_escalation())

    async def _send_escalation(self) -> None:
        """Send escalation notification to additional contacts."""
        name = self.person_name
        room = self.last_motion_room or "—"
        time_str = self.last_motion_time.strftime("%H:%M") if self.last_motion_time else "—"
        title = self._msg("escalation_title", name=name)
        message = self._msg(
            "escalation_message",
            name=name,
            room=room,
            time=time_str,
            delay=self.escalation_delay_minutes,
        )

        tasks = []
        for svc_full in self.escalation_services:
            tasks.append(self._send_ha_notify(svc_full, title, message))
        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))
        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))
        if self.callmebot_phones:
            for phone in self.callmebot_phones:
                tasks.append(self._send_whatsapp(phone, title, message))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Caregiver [%s]: escalation error: %s", self.person_name, result
                    )
        _LOGGER.warning(
            "Caregiver [%s]: escalation sent to %d service(s)",
            self.person_name, len(self.escalation_services),
        )

    async def _send_ha_notify(self, svc_full: str, title: str, message: str) -> None:
        """Send via a HA notify service."""
        parts = svc_full.split(".", 1)
        if len(parts) != 2:
            _LOGGER.warning(
                "Caregiver [%s]: invalid notify service: %s", self.person_name, svc_full
            )
            return
        domain, service = parts
        await self.hass.services.async_call(
            domain, service, {"title": title, "message": message}, blocking=False,
        )
        _LOGGER.info(
            "Caregiver [%s]: notification sent via %s", self.person_name, svc_full
        )

    async def _send_telegram(self, chat_id: str, title: str, message: str) -> None:
        """Send a Telegram message to a single chat_id."""
        import aiohttp
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"*{title}*\n{message}",
            "parse_mode": "Markdown",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info(
                        "Caregiver [%s]: Telegram sent to %s", self.person_name, chat_id
                    )
                else:
                    body = await resp.text()
                    _LOGGER.error(
                        "Caregiver [%s]: Telegram error %d for %s: %s",
                        self.person_name, resp.status, chat_id, body,
                    )

    async def _send_ntfy(self, title: str, message: str) -> None:
        """Send a notification via ntfy.sh (or self-hosted ntfy)."""
        import aiohttp
        url = f"{self.ntfy_server.rstrip('/')}/{self.ntfy_topic}"
        headers = {
            "Title": title,
            "Priority": "high",
            "Tags": "warning,house",
            "Content-Type": "text/plain; charset=utf-8",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201):
                    _LOGGER.info(
                        "Caregiver [%s]: ntfy sent to %s/%s",
                        self.person_name, self.ntfy_server, self.ntfy_topic,
                    )
                else:
                    body = await resp.text()
                    _LOGGER.error(
                        "Caregiver [%s]: ntfy error %d: %s",
                        self.person_name, resp.status, body,
                    )

    async def _send_whatsapp(self, phone: str, title: str, message: str) -> None:
        """Send a WhatsApp message via Callmebot free API."""
        import aiohttp
        import urllib.parse
        text = urllib.parse.quote(f"{title}\n{message}")
        url = (
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={phone}&text={text}&apikey={self.callmebot_api_key}"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info(
                        "Caregiver [%s]: WhatsApp sent to %s", self.person_name, phone
                    )
                else:
                    body = await resp.text()
                    _LOGGER.error(
                        "Caregiver [%s]: WhatsApp error %d for %s: %s",
                        self.person_name, resp.status, phone, body,
                    )

    # -----------------------------------------------------------------
    # AI message generation
    # -----------------------------------------------------------------

    async def _generate_message(self) -> str:
        """Generate alert message, optionally via AI."""
        now = datetime.now().astimezone()
        minutes = self.minutes_since_motion or 0
        hours = minutes // 60
        mins_rem = minutes % 60

        lang = self._get_lang()
        weekday_list = WEEKDAYS.get(lang, WEEKDAYS["en"])
        last_time_str = (
            self.last_motion_time.strftime("%H:%M") if self.last_motion_time else "—"
        )
        last_room = self.last_motion_room or "—"
        weekday = weekday_list[now.weekday()]

        tmpl_vars = dict(
            name=self.person_name,
            room=last_room,
            time=last_time_str,
            now=now.strftime("%H:%M"),
            weekday=weekday,
            hours=hours,
            mins=mins_rem,
            start=self.active_start,
            end=self.active_end,
        )
        fallback = self._msg("inactivity_fallback", **tmpl_vars)

        resolved_key = self._resolve_ai_key()
        if not self.ai_enabled or not resolved_key:
            return fallback

        prompt = self._msg("ai_prompt", **tmpl_vars)

        try:
            if self.ai_provider == AI_PROVIDER_GROQ:
                return await self._call_groq(prompt, fallback, resolved_key)
            elif self.ai_provider == AI_PROVIDER_ANTHROPIC:
                return await self._call_anthropic(prompt, fallback, resolved_key)
            elif self.ai_provider == AI_PROVIDER_OPENAI:
                return await self._call_openai(prompt, fallback, resolved_key)
        except Exception as exc:
            _LOGGER.error("Caregiver [%s]: AI call failed: %s", self.person_name, exc)

        return fallback

    async def _call_groq(self, prompt: str, fallback: str, api_key: str = "") -> str:
        import aiohttp
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key or self.ai_api_key}", "Content-Type": "application/json"}
        payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "max_tokens": 150, "temperature": 0.4}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                _LOGGER.error("Groq API error %d: %s", resp.status, await resp.text())
        return fallback

    async def _call_anthropic(self, prompt: str, fallback: str, api_key: str = "") -> str:
        import aiohttp
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": api_key or self.ai_api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        payload = {"model": "claude-haiku-4-5-20251001", "max_tokens": 150, "messages": [{"role": "user", "content": prompt}]}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"].strip()
                _LOGGER.error("Anthropic API error %d: %s", resp.status, await resp.text())
        return fallback

    async def _call_openai(self, prompt: str, fallback: str, api_key: str = "") -> str:
        import aiohttp
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key or self.ai_api_key}", "Content-Type": "application/json"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 150, "temperature": 0.4}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                _LOGGER.error("OpenAI API error %d: %s", resp.status, await resp.text())
        return fallback

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _resolve_ai_key(self) -> str:
        """
        Hämtar API-nyckel för konfigurerad AI-provider.
        Prioritet: AI Hub (input_text.ai_hub_*) → egna config-entry-nyckeln.
        AI Hub är valfritt – fungerar utan det installerat.
        """
        _bad = {"", "unknown", "unavailable", "none"}
        hub_map = {
            "groq":      "input_text.ai_hub_groq_key",
            "anthropic": "input_text.ai_hub_anthropic_key",
            "openai":    "input_text.ai_hub_openai_key",
        }
        hub_entity = hub_map.get(self.ai_provider)
        if hub_entity:
            st = self.hass.states.get(hub_entity)
            hub_key = (st.state if st else "").strip()
            if hub_key and hub_key not in _bad:
                return hub_key
        return self.ai_api_key

    def _get_lang(self) -> str:
        """Resolve the active language code (en or sv)."""
        lang = self.language
        if lang == "auto" or lang not in MESSAGES:
            ha_lang = getattr(self.hass.config, "language", "en") or "en"
            lang = ha_lang.split("-")[0].lower()
        return lang if lang in MESSAGES else "en"

    def _msg(self, key: str, **kwargs) -> str:
        """Return a formatted message template for the active language."""
        tmpl = MESSAGES.get(self._get_lang(), MESSAGES["en"]).get(key, "")
        return tmpl.format(**kwargs) if kwargs else tmpl

    def _within_active_hours(self) -> bool:
        """Return True if current time is within configured active hours."""
        now = datetime.now()
        try:
            start_h, start_m = map(int, self.active_start.split(":"))
            end_h, end_m = map(int, self.active_end.split(":"))
        except ValueError:
            return True

        start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

        if start <= end:
            return start <= now <= end
        return now >= start or now <= end
