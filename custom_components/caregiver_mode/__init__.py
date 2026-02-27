"""Caregiver Mode – AI-assisted motion monitoring for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import (
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
    DEFAULT_NTFY_SERVER,
    CHECK_INTERVAL,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_ALERT,
    STATUS_UNKNOWN,
    AI_PROVIDER_GROQ,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OPENAI,
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

        # State
        self.last_motion_time: datetime | None = None
        self.last_motion_room: str | None = None
        self.alert_active: bool = False
        self.alert_since: datetime | None = None
        self.alert_reason: str | None = None
        self.alert_ai_message: str | None = None
        self._last_alert_sent: datetime | None = None

        # Subscriptions
        self._unsub_state: Callable | None = None
        self._unsub_timer: Callable | None = None

    # -----------------------------------------------------------------
    # Setup / teardown
    # -----------------------------------------------------------------

    async def async_setup(self) -> None:
        """Subscribe to sensor state changes and start periodic check."""
        sensor_ids = list(self.sensor_room_map.keys())
        if sensor_ids:
            self._unsub_state = async_track_state_change_event(
                self.hass, sensor_ids, self._on_motion_event
            )
            _LOGGER.debug(
                "Caregiver [%s]: tracking %d sensors", self.person_name, len(sensor_ids)
            )

        self._unsub_timer = async_track_time_interval(
            self.hass,
            self._periodic_check,
            timedelta(seconds=CHECK_INTERVAL),
        )

    async def async_teardown(self) -> None:
        """Remove subscriptions."""
        if self._unsub_state:
            self._unsub_state()
        if self._unsub_timer:
            self._unsub_timer()

    # -----------------------------------------------------------------
    # Callbacks for entities
    # -----------------------------------------------------------------

    def register_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    def unregister_callback(self, cb: Callable) -> None:
        self._callbacks.discard(cb) if hasattr(self._callbacks, "discard") else None
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
            return  # Only react to active motion

        entity_id = event.data.get("entity_id", "")
        room = self.sensor_room_map.get(entity_id, entity_id)

        _LOGGER.debug("Caregiver [%s]: motion in %s", self.person_name, room)

        self.last_motion_time = datetime.now().astimezone()
        self.last_motion_room = room

        # If alert was active, clear it
        if self.alert_active:
            _LOGGER.info(
                "Caregiver [%s]: motion detected — clearing alert", self.person_name
            )
            self.alert_active = False
            self.alert_since = None
            self.alert_reason = None
            self.alert_ai_message = None

        self._notify_entities()

    # -----------------------------------------------------------------
    # Periodic check
    # -----------------------------------------------------------------

    @callback
    def _periodic_check(self, now=None) -> None:
        """Run every CHECK_INTERVAL seconds."""
        if not self._within_active_hours():
            # Outside active hours: clear alerts, nothing to do
            if self.alert_active:
                self.alert_active = False
                self._notify_entities()
            return

        if self.last_motion_time is None:
            return  # Never seen motion yet

        minutes = self.minutes_since_motion
        if minutes is None:
            return

        threshold_minutes = self.alert_delay_hours * 60

        if minutes >= threshold_minutes:
            if not self.alert_active:
                # Trigger new alert
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
                # Send alert async (fire-and-forget from sync callback)
                self.hass.async_create_task(self._send_alert())
            else:
                # Alert already active — check cooldown for repeat notification
                if self._last_alert_sent is not None:
                    elapsed = datetime.now().astimezone() - self._last_alert_sent
                    cooldown = timedelta(hours=self.alert_cooldown_hours)
                    if elapsed >= cooldown:
                        self.hass.async_create_task(self._send_alert())

    # -----------------------------------------------------------------
    # Alert sending
    # -----------------------------------------------------------------

    async def _send_alert(self) -> None:
        """Generate AI message (if enabled) and push notifications via all channels."""
        message = await self._generate_message()
        self.alert_ai_message = message
        self._last_alert_sent = datetime.now().astimezone()
        self._notify_entities()

        title = f"Caregiver – {self.person_name}"
        tasks = []

        # HA notify channels
        for svc_full in [self.notify_primary, self.notify_secondary]:
            if svc_full:
                tasks.append(self._send_ha_notify(svc_full, title, message))

        # Telegram — one task per chat_id
        if self.telegram_bot_token and self.telegram_chat_ids:
            for chat_id in self.telegram_chat_ids:
                tasks.append(self._send_telegram(chat_id, title, message))

        # Ntfy
        if self.ntfy_topic:
            tasks.append(self._send_ntfy(title, message))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.error("Caregiver [%s]: notification channel error: %s", self.person_name, result)

    async def _send_ha_notify(self, svc_full: str, title: str, message: str) -> None:
        """Send via a HA notify service."""
        parts = svc_full.split(".", 1)
        if len(parts) != 2:
            _LOGGER.warning("Caregiver [%s]: invalid notify service: %s", self.person_name, svc_full)
            return
        domain, service = parts
        await self.hass.services.async_call(
            domain,
            service,
            {"title": title, "message": message},
            blocking=False,
        )
        _LOGGER.info("Caregiver [%s]: notification sent via %s", self.person_name, svc_full)

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
                        "Caregiver [%s]: Telegram notification sent to %s",
                        self.person_name, chat_id,
                    )
                else:
                    body = await resp.text()
                    _LOGGER.error(
                        "Caregiver [%s]: Telegram error %d for chat %s: %s",
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
                        "Caregiver [%s]: ntfy notification sent to %s/%s",
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
        """Call Groq API for message generation."""
        import aiohttp
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.4,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    body = await resp.text()
                    _LOGGER.error("Groq API error %d: %s", resp.status, body)
        return fallback

    async def _call_anthropic(self, prompt: str, fallback: str) -> str:
        """Call Anthropic Claude API for message generation."""
        import aiohttp
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.ai_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 150,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"].strip()
                else:
                    body = await resp.text()
                    _LOGGER.error("Anthropic API error %d: %s", resp.status, body)
        return fallback

    async def _call_openai(self, prompt: str, fallback: str) -> str:
        """Call OpenAI API for message generation."""
        import aiohttp
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.4,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    body = await resp.text()
                    _LOGGER.error("OpenAI API error %d: %s", resp.status, body)
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
            return True  # If parsing fails, assume always active

        start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

        if start <= end:
            return start <= now <= end
        # Overnight range (e.g. 22:00–06:00)
        return now >= start or now <= end
