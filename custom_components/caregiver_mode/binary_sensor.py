"""Binary sensor for Caregiver Mode alert."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_PERSON_NAME, SUFFIX_ALERT


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Caregiver Mode binary sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    person_name = entry.data[CONF_PERSON_NAME]
    slug = person_name.lower().replace(" ", "_")

    async_add_entities([CaregiverAlertBinarySensor(coordinator, entry, slug, person_name)])


class CaregiverAlertBinarySensor(BinarySensorEntity):
    """Binary sensor: on when alert is active."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = "problem"

    def __init__(self, coordinator, entry: ConfigEntry, slug: str, person_name: str) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._slug = slug
        self._person_name = person_name
        coordinator.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_callback(self.async_write_ha_state)

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self._slug}_{SUFFIX_ALERT}"

    @property
    def name(self) -> str:
        return "Alert Active"

    @property
    def icon(self) -> str:
        return "mdi:bell-alert" if self.is_on else "mdi:bell-check"

    @property
    def is_on(self) -> bool:
        return self._coordinator.alert_active

    @property
    def extra_state_attributes(self) -> dict:
        c = self._coordinator
        attrs = {
            "alert_since": c.alert_since.isoformat() if c.alert_since else None,
            "alert_reason": c.alert_reason,
            "ai_message": c.alert_ai_message,
        }
        return attrs

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Caregiver – {self._person_name}",
            "manufacturer": "Caregiver Mode",
            "model": "Motion Monitor",
            "entry_type": "service",
        }
