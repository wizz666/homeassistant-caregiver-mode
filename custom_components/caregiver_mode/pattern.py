"""Pattern learning for Caregiver Mode V3.0."""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import PATTERN_MIN_DAYS, PATTERN_HISTORY_DAYS

_LOGGER = logging.getLogger(__name__)
STORAGE_DIR = "/config/.storage"


def _minutes_to_hhmm(minutes: float) -> str:
    """Convert minutes from midnight to HH:MM string."""
    h = int(minutes) // 60
    m = int(minutes) % 60
    return f"{h:02d}:{m:02d}"


class CaregiverPatternLearner:
    """Learns and tracks daily movement patterns for anomaly detection."""

    def __init__(self, slug: str, hass: "HomeAssistant") -> None:
        self._slug = slug
        self._hass = hass
        self._storage_path = f"{STORAGE_DIR}/caregiver_pattern_{slug}.json"

        # Today's running data (reset nightly at 02:00)
        self._today_first_motion_minutes: int | None = None
        self._today_hourly_active: set[int] = set()

        # Persisted data
        self._history: list[dict] = []
        self._model: dict = {}

    # ------------------------------------------------------------------
    # Runtime recording
    # ------------------------------------------------------------------

    def record_motion(self, timestamp: datetime, room: str) -> None:
        """Record a motion event — called from coordinator's motion handler."""
        minutes_from_midnight = timestamp.hour * 60 + timestamp.minute
        if self._today_first_motion_minutes is None:
            self._today_first_motion_minutes = minutes_from_midnight
        self._today_hourly_active.add(timestamp.hour)
        _LOGGER.debug(
            "CaregiverPattern [%s]: motion recorded at %s (room=%s)",
            self._slug, timestamp.strftime("%H:%M"), room,
        )

    # ------------------------------------------------------------------
    # Nightly finalization
    # ------------------------------------------------------------------

    def close_day(self, day: date) -> None:
        """Finalize yesterday's data and add to history. Called at 02:00."""
        dow = day.weekday()  # 0=Monday … 6=Sunday
        entry = {
            "date": day.isoformat(),
            "dow": dow,
            "first_motion_minutes": self._today_first_motion_minutes,
            "hourly_active": {str(h): True for h in self._today_hourly_active},
        }
        self._history.append(entry)

        # Trim to last PATTERN_HISTORY_DAYS days
        if len(self._history) > PATTERN_HISTORY_DAYS:
            self._history = self._history[-PATTERN_HISTORY_DAYS:]

        # Reset today's tracking for the new day
        self._today_first_motion_minutes = None
        self._today_hourly_active = set()

        _LOGGER.info(
            "CaregiverPattern [%s]: day %s closed (first motion: %s), %d days in history",
            self._slug,
            day.isoformat(),
            _minutes_to_hhmm(entry["first_motion_minutes"])
            if entry["first_motion_minutes"] is not None
            else "none",
            len(self._history),
        )

    # ------------------------------------------------------------------
    # Model computation
    # ------------------------------------------------------------------

    def compute_model(self) -> None:
        """Recompute statistical model from history."""
        if not self._history:
            self._model = {}
            return

        # Group entries per weekday
        by_dow: dict[int, list[dict]] = {i: [] for i in range(7)}
        for entry in self._history:
            dow = entry.get("dow")
            if dow is not None:
                by_dow[int(dow)].append(entry)

        days_per_dow: dict[str, int] = {}
        first_motion: dict[str, dict] = {}
        hourly_prob: dict[str, dict] = {}

        for dow, entries in by_dow.items():
            if not entries:
                continue
            n = len(entries)
            days_per_dow[str(dow)] = n

            # First motion: mean and std (in minutes from midnight)
            fm_values = [
                e["first_motion_minutes"]
                for e in entries
                if e.get("first_motion_minutes") is not None
            ]
            if fm_values:
                mean_val = sum(fm_values) / len(fm_values)
                if len(fm_values) > 1:
                    variance = sum((x - mean_val) ** 2 for x in fm_values) / (len(fm_values) - 1)
                    std_val = math.sqrt(variance)
                else:
                    std_val = 30.0  # Default 30 min std if only one data point
                first_motion[str(dow)] = {
                    "mean": round(mean_val, 1),
                    "std": round(std_val, 1),
                }
            else:
                first_motion[str(dow)] = {"mean": None, "std": None}

            # Hourly probability: fraction of days with at least one motion in that hour
            hour_counts: dict[str, int] = {}
            for entry in entries:
                for h_str in entry.get("hourly_active", {}).keys():
                    hour_counts[h_str] = hour_counts.get(h_str, 0) + 1
            hourly_prob[str(dow)] = {
                h: round(count / n, 3)
                for h, count in hour_counts.items()
            }

        self._model = {
            "days_per_dow": days_per_dow,
            "first_motion": first_motion,
            "hourly_prob": hourly_prob,
            "last_computed": datetime.now().astimezone().isoformat(),
        }
        _LOGGER.info(
            "CaregiverPattern [%s]: model computed (%d history days)",
            self._slug, len(self._history),
        )

    # ------------------------------------------------------------------
    # Anomaly scoring
    # ------------------------------------------------------------------

    def get_anomaly_score(
        self, now: datetime, active_start: str
    ) -> tuple[int, str]:
        """
        Compute anomaly score (0–100) for the current moment.
        Returns (-1, reason_string) if not enough data yet.
        """
        if not self._model or not self._history:
            return -1, "Not enough data"

        total_days = sum(self._model.get("days_per_dow", {}).values())
        if total_days < PATTERN_MIN_DAYS:
            return -1, f"Learning ({total_days}/{PATTERN_MIN_DAYS} days)"

        dow = str(now.weekday())
        current_minutes = now.hour * 60 + now.minute
        current_hour = now.hour

        try:
            active_start_hour = int(active_start.split(":")[0])
        except (ValueError, IndexError):
            active_start_hour = 7

        # ------------------------------------------------------------------
        # Check 1: First motion (weight 65%)
        # ------------------------------------------------------------------
        score_1 = 0
        reason_1 = ""
        fm_model = self._model.get("first_motion", {}).get(dow)

        if fm_model and fm_model.get("mean") is not None:
            expected_mean = fm_model["mean"]
            expected_std = max(fm_model.get("std") or 30.0, 5.0)  # min 5 min std
            expected_hhmm = _minutes_to_hhmm(expected_mean)

            if self._today_first_motion_minutes is not None:
                score_1 = 0
                reason_1 = (
                    f"First motion at {_minutes_to_hhmm(self._today_first_motion_minutes)}"
                    f" (expected ~{expected_hhmm})"
                )
            elif current_minutes < expected_mean + expected_std:
                score_1 = 0
                reason_1 = f"Within normal range (expected ~{expected_hhmm})"
            elif current_minutes < expected_mean + 2 * expected_std:
                score_1 = 50
                reason_1 = (
                    f"1–2σ late – expected ~{expected_hhmm},"
                    f" now {now.strftime('%H:%M')}"
                )
            elif current_minutes < expected_mean + 3 * expected_std:
                score_1 = 80
                reason_1 = (
                    f"2–3σ late – expected ~{expected_hhmm},"
                    f" now {now.strftime('%H:%M')}"
                )
            else:
                score_1 = 100
                reason_1 = (
                    f">3σ late – expected ~{expected_hhmm},"
                    f" now {now.strftime('%H:%M')}"
                )
        else:
            score_1 = 0
            reason_1 = "No data for today's weekday"

        # ------------------------------------------------------------------
        # Check 2: Hourly activity (weight 35%)
        # ------------------------------------------------------------------
        score_2 = 0
        reason_2 = ""
        hourly_prob = self._model.get("hourly_prob", {}).get(dow, {})

        if hourly_prob and current_hour > active_start_hour:
            missed = 0
            expected_active_hours = 0
            for hour in range(active_start_hour, current_hour):
                p = hourly_prob.get(str(hour), 0.0)
                if p >= 0.7:
                    expected_active_hours += 1
                    if hour not in self._today_hourly_active:
                        missed += 1

            if expected_active_hours > 0:
                score_2 = int(missed / expected_active_hours * 100)
                reason_2 = (
                    f"Missed {missed}/{expected_active_hours} expected active hours"
                    if missed > 0
                    else "All expected hours have activity"
                )
            else:
                reason_2 = "No expected active hours yet"
        else:
            reason_2 = "Too early to check hourly pattern"

        # ------------------------------------------------------------------
        # Combined score
        # ------------------------------------------------------------------
        combined = int(score_1 * 0.65 + score_2 * 0.35)

        if score_1 > 0 and reason_2 and score_2 > 0:
            reason = f"{reason_1}; {reason_2}"
        elif score_1 > 0:
            reason = reason_1
        elif score_2 > 0:
            reason = reason_2
        else:
            reason = reason_1 or reason_2 or "Normal"

        return combined, reason

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def days_learned(self) -> int:
        """Number of days in history."""
        return len(self._history)

    @property
    def confidence(self) -> str:
        """Confidence level based on amount of data."""
        n = self.days_learned
        if n < PATTERN_MIN_DAYS:
            return "none"
        if n < 14:
            return "low"
        if n < 30:
            return "medium"
        return "high"

    @property
    def expected_first_motion_today(self) -> str | None:
        """Return expected first motion time for today as HH:MM string, or None."""
        if not self._model:
            return None
        dow = str(datetime.now().weekday())
        fm = self._model.get("first_motion", {}).get(dow)
        if fm and fm.get("mean") is not None:
            return _minutes_to_hhmm(fm["mean"])
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load pattern data from storage file."""
        try:
            if not os.path.exists(self._storage_path):
                _LOGGER.debug(
                    "CaregiverPattern [%s]: no storage file, starting fresh", self._slug
                )
                return
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._history = data.get("history", [])
            self._model = data.get("model", {})
            _LOGGER.info(
                "CaregiverPattern [%s]: loaded %d history entries",
                self._slug, len(self._history),
            )
        except Exception as exc:
            _LOGGER.error(
                "CaregiverPattern [%s]: failed to load storage: %s", self._slug, exc
            )

    async def async_save(self) -> None:
        """Save pattern data to storage file."""
        try:
            os.makedirs(STORAGE_DIR, exist_ok=True)
            data = {
                "version": 1,
                "slug": self._slug,
                "history": self._history,
                "model": self._model,
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            _LOGGER.debug(
                "CaregiverPattern [%s]: saved %d history entries",
                self._slug, len(self._history),
            )
        except Exception as exc:
            _LOGGER.error(
                "CaregiverPattern [%s]: failed to save storage: %s", self._slug, exc
            )
