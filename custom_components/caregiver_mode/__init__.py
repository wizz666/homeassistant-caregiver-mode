"""Caregiver Mode – AI-assisted motion monitoring for Home Assistant."""
from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
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
    DEFAULT_NTFY_SERVER,
    DEFAULT_DEPARTURE_DELAY,
    DEFAULT_OLLAMA_URL,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_GROQ_VISION_MODEL,
    DEFAULT_FALL_CONFIRM_COUNT,
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
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]

WEEKDAYS_SV = [
    "måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Caregiver Mode from a config entry."""
    coordinator = CaregiverCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

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

        # Subscriptions
        self._unsub_motion: Callable | None = None
        self._unsub_exit: Callable | None = None
        self._unsub_tracker: Callable | None = None
        self._unsub_timer: Callable | None = None
        self._unsub_fall_timer: Callable | None = None

    # -----------------------------------------------------------------
    # Setup / teardown
    # -----------------------------------------------------------------

    async def async_setup(self) -> None:
        """Subscribe to sensor state changes and start periodic check."""
        # Motion sensors
        sensor_ids = list(self.sensor_room_map.keys())
        if sensor_ids:
            self._unsub_motion = async_track_state_change_event(
                self.hass, sensor_ids, self._on_motion_event
            )
            _LOGGER.debug(
                "Caregiver [%s]: tracking %d motion sensors", self.person_name, len(sensor_ids)
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
            self._unsub_exit,
            self._unsub_tracker,
            self._unsub_timer,
            self._unsub_fall_timer,
        ]:
            if unsub:
                unsub()
        if self._departure_check_cancel:
            self._departure_check_cancel()

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

        self.last_motion_time = datetime.now().astimezone()
        self.last_motion_room = room

        if self.alert_active:
            _LOGGER.info(
                "Caregiver [%s]: motion detected — clearing inactivity alert", self.person_name
            )
            self.alert_active = False
            self.alert_since = None
            self.alert_reason = None
            self.alert_ai_message = None

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

        messages: dict[str, tuple[str, str]] = {
            "tracker_left": (
                f"📱 {name} har lämnat hemmet",
                f"{name}s telefon har lämnat hemnätverket.",
            ),
            "left_confirmed": (
                f"🚶 {name} har lämnat hemmet",
                f"Dörren öppnades och stängdes, ingen rörelse inomhus och telefonen är borta.",
            ),
            "left_likely": (
                f"🚪 {name} kan ha lämnat hemmet",
                f"Ytterdörren öppnades och stängdes men inga rörelsesensorer registrerade rörelse efteråt.",
            ),
            "forgot_phone": (
                f"⚠️ {name} kan ha lämnat hemmet utan telefonen",
                f"Dörren öppnades och stängdes, ingen rörelse inomhus — men telefonen är kvar. Har {name} glömt den?",
            ),
            "returned_home": (
                f"🏠 {name} är hemma igen",
                f"{name}s telefon är tillbaka i hemnätverket.",
            ),
        }

        title, message = messages.get(scenario, (f"Caregiver – {name}", scenario))

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
        title = f"🚨 FALL DETEKTERAT – {name}"
        message = (
            f"{name} kan ha fallit. Kameraanalysen visade en person liggande på golvet. "
            f"Kontrollera omedelbart! (kl {now_str})"
        )

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
                self.alert_reason = (
                    f"Ingen rörelse på {minutes} minuter "
                    f"(gräns {self.alert_delay_hours} timmar)"
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
    # Inactivity alert sending
    # -----------------------------------------------------------------

    async def _send_alert(self) -> None:
        """Generate AI message (if enabled) and push notifications via all channels."""
        message = await self._generate_message()
        self.alert_ai_message = message
        self._last_alert_sent = datetime.now().astimezone()
        self._notify_entities()

        title = f"⚠️ Caregiver – {self.person_name}"
        tasks = []

        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(self._send_ha_notify(svc_full, title, message))

        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))

        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.error(
                    "Caregiver [%s]: notification channel error: %s",
                    self.person_name, result,
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

    # -----------------------------------------------------------------
    # AI message generation
    # -----------------------------------------------------------------

    async def _generate_message(self) -> str:
        """Generate alert message, optionally via AI."""
        now = datetime.now().astimezone()
        minutes = self.minutes_since_motion or 0
        hours = minutes // 60
        mins_rem = minutes % 60

        last_time_str = (
            self.last_motion_time.strftime("%H:%M") if self.last_motion_time else "okänt"
        )
        last_room = self.last_motion_room or "okänt rum"
        weekday = WEEKDAYS_SV[now.weekday()]

        fallback = (
            f"{self.person_name} registrerades senast i {last_room} kl {last_time_str}. "
            f"Det är nu {now.strftime('%H:%M')} ({weekday}) — "
            f"{hours}h {mins_rem}min utan rörelse."
        )

        if not self.ai_enabled or not self.ai_api_key:
            return fallback

        prompt = (
            f"Person: {self.person_name}\n"
            f"Normala aktiva timmar: {self.active_start}–{self.active_end}\n"
            f"Senaste registrerade rörelse: {last_time_str} i {last_room}\n"
            f"Nuvarande tid: {now.strftime('%H:%M')}\n"
            f"Dag: {weekday}\n"
            f"Tid sedan senaste rörelse: {hours}h {mins_rem}min\n\n"
            "Skriv ett kort, lugnt SMS på svenska som informerar familjen om situationen. "
            "Max 2 meningar. Nämn specifik tid och rum. Undvik alarmism. "
            "Ge bara meddelandetexten, inget annat."
        )

        try:
            if self.ai_provider == AI_PROVIDER_GROQ:
                return await self._call_groq(prompt, fallback)
            elif self.ai_provider == AI_PROVIDER_ANTHROPIC:
                return await self._call_anthropic(prompt, fallback)
            elif self.ai_provider == AI_PROVIDER_OPENAI:
                return await self._call_openai(prompt, fallback)
        except Exception as exc:
            _LOGGER.error("Caregiver [%s]: AI call failed: %s", self.person_name, exc)

        return fallback

    async def _call_groq(self, prompt: str, fallback: str) -> str:
        import aiohttp
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
        payload = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt}], "max_tokens": 150, "temperature": 0.4}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                _LOGGER.error("Groq API error %d: %s", resp.status, await resp.text())
        return fallback

    async def _call_anthropic(self, prompt: str, fallback: str) -> str:
        import aiohttp
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": self.ai_api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        payload = {"model": "claude-haiku-4-5-20251001", "max_tokens": 150, "messages": [{"role": "user", "content": prompt}]}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"].strip()
                _LOGGER.error("Anthropic API error %d: %s", resp.status, await resp.text())
        return fallback

    async def _call_openai(self, prompt: str, fallback: str) -> str:
        import aiohttp
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
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
