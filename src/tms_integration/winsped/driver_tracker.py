import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta

import requests

from src.tms_integration.winsped.models.lisin import LisInDriver
from src.tms_integration.winsped.models.types.driver import Driver

logger = logging.getLogger(__name__)


class DriverTracker:
    def __init__(
        self,
        api_key: str,
        api_name: str,
        drivers_ids_path: str,
        lis_winsped
    ):
        self.api_key = api_key
        self.api_name = api_name
        self.lis_winsped = lis_winsped
        self.running = True
        self.lock = threading.Lock()
        self.update_counter = 0

        self.latest_drivers: dict[str, Driver] = {}
        self._day_start_cache: dict[str, tuple[str, str | None]] = {}
        self.drivers_ids = self._load_driver_list(drivers_ids_path)

        logger.info(
            f"[{self.api_name}] DriverTracker initialized with {len(self.drivers_ids)} drivers"
        )

    @staticmethod
    def _load_driver_list(path: str) -> list:
        with open(path) as f:
            return json.load(f)

    def _fetch_driver(self, driver_id: str) -> dict | None:
        """Fetch time analysis for a single driver from the API."""
        url = (
            f"https://api.fm-track.com/drivers/{driver_id}/current-time-analysis"
            f"?version=1&api_key={self.api_key}"
        )
        try:
            response = requests.get(
                url,
                headers={"Content-Type": "application/json;charset=UTF-8"},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"[{self.api_name}] HTTP error for driver {driver_id}: {e}")
        except requests.exceptions.Timeout:
            logger.error(f"[{self.api_name}] Timeout fetching driver {driver_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.api_name}] Request error for driver {driver_id}: {e}")
        return None

    def _get_cached_day_start(
        self, driver_id: str, calculated_dt: datetime
    ) -> str | None:
        """
        Get cached day start, fetching only if needed.
        Returns the cached value or None if not yet cached for today.
        """
        calculated_str = calculated_dt.strftime("%Y-%m-%d")

        with self.lock:
            cached_entry = self._day_start_cache.get(driver_id)

            if cached_entry is not None:
                cached_date, cached_value = cached_entry
                if cached_date == calculated_dt:
                    return cached_value

            day_start = self._get_driver_day_start(driver_id, calculated_dt)

            self._day_start_cache[driver_id] = (calculated_str, day_start)

            if day_start:
                logger.debug(
                    f"[{self.api_name}] Fetched day_start for driver {driver_id} (cached)"
                )
            else:
                logger.debug(
                    f"[{self.api_name}] No day_start found for driver {driver_id}"
                )

            return day_start

    def _get_driver_day_start(self, driver_id: str, now: datetime) -> str | None:
        url = f"https://api.fm-track.com/driverstate/{driver_id}"

        start_of_day = datetime(
            year=now.year, month=now.month, day=now.day, tzinfo=UTC
        )

        from_datetime = start_of_day.isoformat().replace("+00:00", "Z")
        to_datetime = now.isoformat().replace("+00:00", "Z")

        params = {
            "from_datetime": from_datetime,
            "to_datetime": to_datetime,
            "continuation_token": "",
            "limit": 1,
            "version": 1,
            "api_key": self.api_key,
        }
        try:
            response = requests.get(url, params=params, timeout=30)
            logger.debug(
                f"[{self.api_name}] Status code for {driver_id}: {response.status_code}"
            )

            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                if items:
                    driver_day_start = items[0].get("start_time")
                    return driver_day_start
            else:
                logger.error(
                    f"[{self.api_name}] Error fetching day_start for {driver_id}: {response.text}"
                )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"[{self.api_name}] Request error fetching day_start for {driver_id}: {e}"
            )

        return None

    def _build_driver(self, driver_id: str, data: dict) -> Driver | None:
        """Build a Driver pydantic instance from raw API response."""
        try:
            state = data.get("state", {})
            current_day = data.get("current_day", {})
            current_week = data.get("current_week", {})
            prev_week = data.get("previous_week", {})

            calculated_until = data.get("calculated_until")
            calculated_dt = datetime.fromisoformat(
                calculated_until.replace("Z", "+00:00")
            )
            # calculated_dt = calculated_dt + timedelta(hours=1)
            calculated_until_iso = calculated_dt.isoformat().replace("+00:00", "Z")

            day_regular_duration = (
                current_day.get("driving", {}).get("regular", {}).get("duration", 0)
            )
            day_regular_limit = (
                current_day.get("driving", {})
                .get("regular", {})
                .get("duration_limit", 0)
            )
            day_extra_limit = (
                current_day.get("driving", {}).get("extra", {}).get("duration_limit", 0)
            )
            day_work_duration = current_day.get("working", {}).get("duration", 0)

            day_next_rest = current_day.get("resting", {}).get("next_rest")
            if day_next_rest:
                day_next_rest_dt = datetime.fromisoformat(
                    day_next_rest.replace("Z", "+00:00")
                )
                # day_next_rest_dt = day_next_rest_dt + timedelta(hours=1)
                day_next_rest_iso = day_next_rest_dt.isoformat().replace("+00:00", "Z")
            else:
                day_next_rest_iso = None

            week_drive_limit = current_week.get("driving", {}).get("duration_limit", 0)
            week_drive_duration = current_week.get("driving", {}).get("duration", 0)
            week_work_duration = current_week.get("working", {}).get("duration", 0)

            week_next_rest = current_week.get("resting", {}).get("next_rest")
            if week_next_rest:
                week_next_rest_dt = datetime.fromisoformat(
                    week_next_rest.replace("Z", "+00:00")
                )
                # week_next_rest_dt = week_next_rest_dt + timedelta(hours=1)
                week_next_rest_iso = week_next_rest_dt.isoformat().replace(
                    "+00:00", "Z"
                )
            else:
                week_next_rest_iso = None

            week_start = current_week.get("resting", {}).get("started_at")
            if week_start:
                week_start_dt = datetime.fromisoformat(
                    week_start.replace("Z", "+00:00")
                )
                # week_start_dt = week_start_dt + timedelta(hours=1)
                week_start_iso = week_start_dt.isoformat().replace("+00:00", "Z")
            else:
                week_start_iso = None

            prev_week_drive_duration = prev_week.get("driving", {}).get("duration", 0)
            prev_week_drive_limit = prev_week.get("driving", {}).get(
                "duration_limit", 0
            )
            prev_week_rest = prev_week.get("resting", {}).get("duration", 0)
            dr = Driver(
                stateDate=calculated_dt.strftime("%Y%m%d"),
                stateTime=calculated_dt.strftime("%H%M"),
                driverCard1=driver_id,
                currentActivity=state.get("activity", "UNKNOWN"),
                currentActivityStart=self._parse_iso(state.get("started_at")),
                currentDriveMin=self._to_minutes(state.get("duration")),
                dayDriveRemainMin=self._to_minutes(
                    day_regular_limit - day_regular_duration + day_extra_limit
                ),
                dayDriveMin=self._to_minutes(day_regular_duration),
                dayWorkMin=self._to_minutes(day_work_duration),
                weekDriveMin=self._to_minutes(week_drive_duration),
                weekDriveRemainMin=self._to_minutes(
                    week_drive_limit - week_drive_duration
                ),
                weekWorkMin=self._to_minutes(week_work_duration),
                driverWeekDriveMin=self._to_minutes(week_drive_duration),
                doubleWeekDriveMin=self._to_minutes(
                    week_drive_duration + prev_week_drive_duration
                ),
                doubleWeekDriveRemainMin=self._to_minutes(
                    (prev_week_drive_limit - prev_week_drive_duration)
                    + (week_drive_limit - week_drive_duration)
                ),
                lastWeekRestMin=self._to_minutes(prev_week_rest),
            )

            driverDayStart = self._get_cached_day_start(driver_id, calculated_dt)
            if driverDayStart:
                dr.driverDayStart = self._parse_iso(driverDayStart)

            if day_next_rest:
                dr.dayWorkRemainMin = self._minutes_between_dates(
                    calculated_until_iso, day_next_rest_iso
                )
                dr.dayWorkEnd = self._parse_iso(day_next_rest_iso)
                dr.nextBreakStart = self._parse_iso(day_next_rest_iso)
                dr.nextBreakRemainMin = self._minutes_between_dates(
                    calculated_until_iso, day_next_rest_iso
                )

            if week_next_rest:
                dr.weekWorkRemainMin = self._minutes_between_dates(
                    calculated_until_iso, week_next_rest_iso
                )

            if week_start:
                dr.driverWeekStart = self._parse_iso(week_start_iso)

            return dr

        except Exception as e:
            logger.error(
                f"[{self.api_name}] Failed to build Driver for {driver_id}: {e}"
            )
            return None

    def _fetch_all_drivers(self):
        """Fetch data for every driver in the map and update latest_drivers."""
        logger.info(f"[{self.api_name}] Fetching {len(self.drivers_ids)} drivers...")
        updated = 0
        failed = 0

        for driver_id in self.drivers_ids:
            if not self.running:
                break

            data = self._fetch_driver(driver_id)
            if data is None:
                failed += 1
                continue

            driver = self._build_driver(driver_id, data)
            if driver is None:
                failed += 1
                continue

            with self.lock:
                self.latest_drivers[driver_id] = driver
                self.update_counter += 1
                updated += 1

            time.sleep(0.2)

        logger.info(
            f"[{self.api_name}] Fetch cycle complete — "
            f"updated={updated}, failed={failed}, total={len(self.latest_drivers)}"
        )

    def _send_to_ftp(self):
        """Send all current Driver records to FTP via LisWinSped."""
        with self.lock:
            if not self.latest_drivers:
                logger.warning(f"[{self.api_name}] No driver data to send")
                return
            drivers = list(self.latest_drivers.values())

        try:
            payload = LisInDriver()
            payload.records = drivers
            self.lis_winsped.import_to_ftp(payload, "499", country=self.api_name.split("_")[1])
            logger.info(f"[{self.api_name}] Sent {len(drivers)} driver records to FTP")
        except Exception as e:
            logger.error(f"[{self.api_name}] FTP send failed: {e}")

    @staticmethod
    def _to_minutes(seconds: int | None) -> int | None:
        """Convert seconds to minutes, handling None gracefully."""
        return seconds // 60 if seconds is not None else None

    @staticmethod
    def _parse_iso(value: str | None) -> str | None:
        """Convert ISO timestamp to YYYYMMDD HHMMSS format for Driver validator."""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y%m%d %H%M%S")
        except ValueError:
            return None

    @staticmethod
    def _minutes_between_dates(start_date: str, end_date: str) -> int | None:
        """Calculate minutes between two ISO 8601 dates."""
        if not start_date or not end_date:
            return None

        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

            delta_seconds = int((end_dt - start_dt).total_seconds())
            if delta_seconds >= 0:
                return delta_seconds // 60
            else:
                return 0
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _add_seconds_to_date(iso_date: str, seconds: int) -> str | None:
        """Add seconds to an ISO 8601 date and return the new datetime object."""
        if not iso_date:
            return None

        try:
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            dt = dt + timedelta(seconds=seconds)
            iso_string = dt.isoformat().replace("+00:00", "Z")
            formatted = DriverTracker._parse_iso(iso_string)
            return formatted
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _subtract_seconds_from_date(iso_date: str, seconds: int) -> str | None:
        """Subtract seconds from an ISO 8601 date and return the new datetime object."""
        return DriverTracker._add_seconds_to_date(iso_date, -seconds)

    def run(self, report_interval_minutes: int = 10):
        """Main loop — fetch all drivers every N minutes, send to FTP."""
        logger.info(
            f"[{self.api_name}] DriverTracker started. "
            f"Fetching every {report_interval_minutes} minutes."
        )

        while self.running:
            cycle_start = time.time()

            self._fetch_all_drivers()
            self._send_to_ftp()

            elapsed = time.time() - cycle_start
            sleep_for = max(0, report_interval_minutes * 60 - elapsed)

            logger.info(f"[{self.api_name}] Next fetch in {sleep_for / 60:.1f} minutes")

            for _ in range(int(sleep_for)):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        self.running = False
        logger.info(f"[{self.api_name}] DriverTracker stopped")
