"""Sensors for Caregiver Mode."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_PERSON_NAME,
    STATUS_UNKNOWN,
    SUFFIX_STATUS,
    SUFFIX_LAST_SEEN,
    SUFFIX_LAST_ROOM,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Caregiver Mode sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    person_name = entry.data[CONF_PERSON_NAME]
    slug = person_name.lower().replace(" ", "_")

    async_add_entities(
        [
            CaregiverStatusSensor(coordinator, entry, slug, person_name),
            CaregiverLastSeenSensor(coordinator, entry, slug, person_name),
            CaregiverLastRoomSensor(coordinator, entry, slug, person_name),
        ]
    )


class CaregiverBaseSensor(SensorEntity):
    """Base class for Caregiver sensors."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, slug: str, person_name: str) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._slug = slug
        self._person_name = person_name
        coordinator.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_callback(self.async_write_ha_state)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Caregiver – {self._person_name}",
            "manufacturer": "Caregiver Mode",
            "model": "Motion Monitor",
            "entry_type": "service",
        }


class CaregiverStatusSensor(CaregiverBaseSensor):
    """Sensor reporting current status."""

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._slug}_{SUFFIX_STATUS}"

    @property
    def name(self) -> str:
        return "Status"

    @property
    def icon(self) -> str:
        status = self._coordinator.status
        if status == "active":
            return "mdi:human-greeting"
        if status == "alert":
            return "mdi:alert-circle"
        if status == "inactive":
            return "mdi:sleep"
        return "mdi:help-circle-outline"

    @property
    def native_value(self) -> str:
        return self._coordinator.status

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        return {
            "last_motion_time": c.last_motion_time.isoformat() if c.last_motion_time else None,
            "last_motion_room": c.last_motion_room,
            "active_hours": f"{c.active_start}–{c.active_end}",
            "sensors_count": len(c.sensor_room_map),
            "minutes_since_motion": c.minutes_since_motion,
        }


class CaregiverLastSeenSensor(CaregiverBaseSensor):
    """Sensor reporting last seen timestamp."""

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._slug}_{SUFFIX_LAST_SEEN}"

    @property
    def name(self) -> str:
        return "Last Seen"

    @property
    def icon(self) -> str:
        return "mdi:clock-outline"

    @property
    def native_value(self) -> str | None:
        t = self._coordinator.last_motion_time
        return t.isoformat() if t else None

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        return {
            "minutes_since": c.minutes_since_motion,
            "room": c.last_motion_room,
        }


class CaregiverLastRoomSensor(CaregiverBaseSensor):
    """Sensor reporting last room where motion was detected."""

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._slug}_{SUFFIX_LAST_ROOM}"

    @property
    def name(self) -> str:
        return "Last Room"

    @property
    def icon(self) -> str:
        return "mdi:map-marker"

    @property
    def native_value(self) -> str:
        return self._coordinator.last_motion_room or STATUS_UNKNOWN
