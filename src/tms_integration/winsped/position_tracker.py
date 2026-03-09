import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime

import sseclient

from src.tms_integration.winsped import LisWinSped
from src.tms_integration.winsped.models import LisInPosition
from src.tms_integration.winsped.models.types import Position

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
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

        self.init_database()

        self.load_existing_positions()

        logger.info(f"Tracker initialized for API: {api_name}")

    def init_database(self):
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

    def load_existing_positions(self):
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

    def process_event(self, event_data: str):
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

    def save_to_database(self):
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

    def report_scheduler(self, interval_minutes: int = 10):
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

                self.save_to_database()
                # self.generate_txt_report()
                self.send_to_ftp(self.lis_winsped)
                # self.cleanup_old_reports()

    def send_to_ftp(self, lis_winsped: LisWinSped):
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
            lis_winsped.import_location(payload, "15", self.api_name)
            logger.info(f"[{self.api_name}] Sent {len(positions)} positions to FTP")

    '''
    def generate_txt_report(self):
        """Generate a text file with latest positions of all vehicles in the required format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"vehicle_positions_{timestamp}.txt"
        filepath = os.path.join(self.output_dir, filename)

        with self.lock:
            if not self.latest_positions:
                content = "No vehicle data available yet.\n"
            else:
                lines = []

                for object_id, data in self.latest_positions.items():
                    position = data.get('position', {})

                    lat = position.get('latitude')
                    lon = position.get('longitude')

                    api_datetime = data.get('datetime', '')

                    date_str, time_str = self.convert_datetime(api_datetime)

                    lat_formatted = self.format_coordinate(lat, 'lat')
                    lon_formatted = self.format_coordinate(lon, 'lon')

                    line = (f"15|{date_str}|{time_str}|{object_id}|0|PosBreite={lat_formatted}|PosLaenge={lon_formatted}|")

                    lines.append(line)

                content = "\n".join(lines)

            with open(filepath, 'w') as f:
                f.write(content)

            # create a symlink or copy to "15_ua.txt" for easy access
            latest_link = os.path.join(self.output_dir, f"15_{self.api_name}.txt")
            try:
                if os.path.exists(latest_link):
                    os.remove(latest_link)
                os.symlink(filename, latest_link)
            except:
                with open(latest_link, 'w') as f:
                    f.write(content)

            logger.info(f"Generated report: {filename} with {len(self.latest_positions)} vehicles")
            return filepath

    def convert_datetime(self, api_datetime):
        """Convert API datetime format to required formats"""
        if not api_datetime:
            return "20000101", "000000"

        try:
            dt = datetime.fromisoformat(api_datetime.replace('Z', '+00:00'))

            date_str = dt.strftime("%Y%m%d")

            time_str = dt.strftime("%H%M%S")

            return date_str, time_str
        except:
            return "20000101", "000000"

    def format_coordinate(self, coord, coord_type):
        """Convert decimal coordinate to GGGNNNND format"""
        if coord is None:
            return "0000000N" if coord_type == 'lat' else "0000000E"

        try:
            coord = float(coord)
            if coord_type == 'lat':
                direction = 'N' if coord >= 0 else 'S'
                coord = abs(coord)
            else:
                direction = 'E' if coord >= 0 else 'W'
                coord = abs(coord)

            degrees = int(coord)
            decimals = int(round((coord - degrees) * 10000))

            # Format: GGG = 3-digit degrees, NNNN = 4-digit decimals
            # Example: 52.2735 -> degrees=52, decimals=2735 -> "0522735N"
            formatted = f"{degrees:03d}{decimals:04d}{direction}"

            return formatted
        except (ValueError, TypeError):
            return "0000000N" if coord_type == 'lat' else "0000000E"
    
    
    def cleanup_old_reports(self, keep_last: int = 0):
        """Delete old report files to save space"""
        try:
            files = [f for f in os.listdir(self.output_dir)
                     if f.startswith(f'vehicle_positions_{self.api_name}_') and f.endswith('.txt')]
            files.sort(reverse=True)

            for old_file in files[keep_last:]:
                os.remove(os.path.join(self.output_dir, old_file))
                logger.debug(f"[{self.api_name}] Removed old report: {old_file}")
        except Exception as e:
            logger.error(f"[{self.api_name}] Error cleaning up old reports: {e}")
    '''

    def sse_listener(self):
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
                        self.process_event(event.data)

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

        self.save_to_database()

        logger.info(f"[{self.api_name}] Final report generated. Goodbye!")

    def run(self, report_interval_minutes: int = 10):
        """Start both the SSE listener and report scheduler"""
        listener_thread = threading.Thread(target=self.sse_listener, daemon=True)
        listener_thread.start()

        self.report_scheduler(report_interval_minutes)
