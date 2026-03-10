import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime

import sseclient

from src.tms_integration.winsped.models import LisInPosition
from src.tms_integration.winsped.models.types import Position
from tms_integration.winsped import LisWinSped

logger = logging.getLogger(__name__)


class PositionTracker:
    def __init__(
        self,
        lis_winsped: LisWinSped,
        api_key: str,
        api_name: str,
        db_path: str = None,
        output_dir: str = "position_reports",
    ):
        self.lis_winsped = lis_winsped
        self.api_key = api_key
        self.api_name = api_name
        self.db_path = db_path or f"positions_{api_name}.db"
        self.output_dir = os.path.join(output_dir, api_name)
        self.latest_positions: dict[str, dict] = {}
        self.last_update_time: dict[str, datetime] = {}
        self.lock = threading.Lock()
        self.running = True
        self.update_counter = 0

        os.makedirs(self.output_dir, exist_ok=True)

        self._init_database()

        self._load_existing_positions()

        logger.info(f"Tracker initialized for API: {api_name}")

    def _init_database(self):
        """Initialize SQLite database with only required fields"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -2000")

            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vehicle_positions (
                    object_id TEXT PRIMARY KEY,
                    datetime TEXT,
                    latitude REAL,
                    longitude REAL,
                    last_seen TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_seen 
                ON vehicle_positions(last_seen)
            """)

            conn.commit()

        logger.info(f"Database initialized for {self.api_name} at {self.db_path}")

    def _load_existing_positions(self):
        """Load existing positions from database on startup"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM vehicle_positions")

                rows = cursor.fetchall()
                with self.lock:
                    for row in rows:
                        data = {
                            "object_id": row["object_id"],
                            "datetime": row["datetime"],
                            "position": {
                                "latitude": row["latitude"],
                                "longitude": row["longitude"],
                            },
                        }

                        self.latest_positions[row["object_id"]] = data
                        if row["last_seen"]:
                            self.last_update_time[row["object_id"]] = (
                                datetime.fromisoformat(row["last_seen"])
                            )

                logger.info(
                    f"Loaded {len(self.latest_positions)} existing vehicle positions for {self.api_name}"
                )

        except Exception as e:
            logger.error(f"Error loading existing positions for {self.api_name}: {e}")

    def _process_event(self, event_data: str):
        """Process incoming SSE event data"""
        try:
            data = json.loads(event_data)
            object_id = data.get("object_id")

            if not object_id:
                return

            current_time = datetime.now()

            with self.lock:
                simplified_data = {
                    "object_id": object_id,
                    "datetime": data.get("datetime"),
                    "position": {
                        "latitude": data.get("position", {}).get("latitude"),
                        "longitude": data.get("position", {}).get("longitude"),
                    },
                }

                self.latest_positions[object_id] = simplified_data
                self.last_update_time[object_id] = current_time
                self.update_counter += 1

                position = simplified_data.get("position", {})

                if self.update_counter % 5 == 0:
                    logger.info(
                        f"[{self.api_name}] Processed {self.update_counter} total updates. "
                        f"Last: {object_id} at {position.get('latitude')}, {position.get('longitude')}"
                    )
                else:
                    logger.debug(
                        f"[{self.api_name}] Updated vehicle {object_id}: "
                        f"lat={position.get('latitude')}, lon={position.get('longitude')}"
                    )

        except json.JSONDecodeError as e:
            logger.error(f"[{self.api_name}] Error parsing JSON: {e}")
        except Exception as e:
            logger.error(f"[{self.api_name}] Error processing event: {e}")

    def _save_to_database(self):
        """Save all latest positions to database - only required fields"""
        with self.lock:
            if not self.latest_positions:
                return

            start_time = time.time()

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("BEGIN")
                cursor = conn.cursor()

                for object_id, data in self.latest_positions.items():
                    try:
                        position = data.get("position", {})
                        last_seen = self.last_update_time.get(object_id, datetime.now())

                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO vehicle_positions 
                            (object_id, datetime, latitude, longitude, last_seen, last_updated)
                            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                            (
                                object_id,
                                data.get("datetime"),
                                position.get("latitude"),
                                position.get("longitude"),
                                last_seen.isoformat(),
                            ),
                        )

                    except Exception as e:
                        logger.error(
                            f"[{self.api_name}] Error saving vehicle {object_id}: {e}"
                        )
                        conn.rollback()
                        return

                conn.commit()

            elapsed = time.time() - start_time
            logger.info(
                f"[{self.api_name}] Saved {len(self.latest_positions)} vehicles to database in {elapsed:.3f} seconds"
            )

    def _report_scheduler(self, interval_minutes: int = 10):
        """Generate reports at regular intervals"""
        logger.info(
            f"[{self.api_name}] Report scheduler started. Generating reports every {interval_minutes} minutes"
        )

        while self.running:
            for _ in range(interval_minutes * 60):
                if not self.running:
                    break
                time.sleep(1)

            if self.running:
                logger.info(
                    f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{self.api_name}] Generating scheduled report..."
                )

                self._save_to_database()
                self._send_to_ftp(self.lis_winsped)

    def _send_to_ftp(self, lis_winsped: LisWinSped):
        with self.lock:
            if not self.latest_positions:
                logger.warning(f"[{self.api_name}] No positions to send")
                return

            positions = []
            for object_id, data in self.latest_positions.items():
                try:
                    api_datetime = data.get("datetime", "")
                    dt = datetime.fromisoformat(api_datetime.replace("Z", "+00:00"))
                    position = data.get("position", {})

                    positions.append(
                        Position(
                            positionDate=dt.strftime("%Y%m%d"),
                            positionTime=dt.strftime("%H%M%S"),
                            partnerId=object_id,
                            posBreite=str(position.get("latitude")),
                            posLaenge=str(position.get("longitude")),
                        )
                    )

                except Exception as e:
                    logger.error(
                        f"[{self.api_name}] Error creating Position for {object_id}: {e}"
                    )
            if not positions:
                return

            payload = LisInPosition()
            payload.records = positions
            lis_winsped.import_to_ftp(payload, "15", country=self.api_name.split("_")[1])
            logger.info(f"[{self.api_name}] Sent {len(positions)} positions to FTP")


    def _sse_listener(self):
        """Listen to SSE stream and process events"""
        url = (
            f"https://api.fm-track.com/object-coordinates-stream"
            f"?version=2&api_key={self.api_key}"
        )

        logger.info(f"[{self.api_name}] Connecting to SSE stream...")

        reconnect_delay = 1
        max_reconnect_delay = 60

        while self.running:
            try:
                client = sseclient.SSEClient(url)
                logger.info(
                    f"[{self.api_name}] Connected to stream. Waiting for data..."
                )
                reconnect_delay = 1

                for event in client:
                    if not self.running:
                        break

                    if event.data:
                        self._process_event(event.data)

            except Exception as e:
                logger.error(f"[{self.api_name}] SSE connection error: {e}")
                if self.running:
                    logger.info(
                        f"[{self.api_name}] Reconnecting in {reconnect_delay} seconds..."
                    )
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    def signal_handler(self, sig, frame):
        """Handle shutdown signals gracefully"""
        logger.info(
            f"\n[{self.api_name}] Shutdown signal received. Generating final report and saving to database..."
        )
        self.running = False

        self._save_to_database()

        logger.info(f"[{self.api_name}] Final report generated. Goodbye!")

    def run(self, report_interval_minutes: int = 10):
        """Start both the SSE listener and report scheduler"""
        listener_thread = threading.Thread(target=self._sse_listener, daemon=True)
        listener_thread.start()

        self._report_scheduler(report_interval_minutes)
