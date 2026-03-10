import logging
import signal
import sys
import threading
import time

from src.tms_integration.winsped import LisWinSped
from src.tms_integration.winsped.driver_tracker import DriverTracker
from src.tms_integration.winsped.position_tracker import PositionTracker

logger = logging.getLogger(__name__)

class MultiAPITracker:
    def __init__(self, lis_winsped: LisWinSped):
        self.lis_winsped = lis_winsped
        self.trackers: list[PositionTracker] = []
        self.threads: list[threading.Thread] = []
        self.running = True

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def add_position_tracker(
        self,
        api_key: str,
        api_name: str,
        report_interval: int = 10
    ):
        """Add a new tracker for an API key"""
        tracker = PositionTracker(
            lis_winsped=self.lis_winsped, api_key=api_key, api_name=api_name
        )
        self.trackers.append((tracker, report_interval))
        logger.info(f"Added tracker for API: {api_name}")
        return tracker

    def add_driver_tracker(
        self,
        api_key: str,
        api_name: str,
        drivers_ids_path: str,
        report_interval: int = 10,
    ):
        """Add a new tracker for an API key"""
        tracker = DriverTracker(
            lis_winsped=self.lis_winsped,
            api_key=api_key,
            api_name=api_name,
            drivers_ids_path=drivers_ids_path,
        )
        self.trackers.append((tracker, report_interval))
        logger.info(f"Added tracker for API: {api_name}")
        return tracker

    def run_tracker(
        self, tracker: PositionTracker | DriverTracker, interval: int
    ):
        """Run a single tracker in its own thread"""
        try:
            if isinstance(tracker, PositionTracker):
                logger.info(f"Running PositionTracker: {tracker.api_name}")
                tracker.run(report_interval_minutes=interval)
            elif isinstance(tracker, DriverTracker):
                logger.info(f"Running DriverTracker: {tracker.api_name}")
                tracker.run(report_interval_minutes=interval)
            else:
                raise TypeError(f"Unknown tracker type: {type(tracker)}")
        except Exception as e:
            logger.error(f"Error in tracker {tracker.api_name}: {e}")

    def start_all(self):
        """Start all trackers in separate threads"""
        for tracker, interval in self.trackers:
            thread = threading.Thread(
                target=self.run_tracker,
                args=(tracker, interval),
                daemon=True,
                name=f"Tracker-{tracker.api_name}",
            )
            thread.start()
            self.threads.append(thread)
            logger.info(f"Started thread for API: {tracker.api_name}")

            time.sleep(1)

        logger.info(
            f"All trackers started. Running {len(self.trackers)} trackers simultaneously."
        )
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.signal_handler(None, None)

    def signal_handler(self, sig, frame):
        """Handle shutdown signals gracefully"""
        logger.info("\nShutdown signal received. Stopping all trackers...")
        self.running = False

        for tracker, _ in self.trackers:
            tracker.running = False

        logger.info("All trackers stopped. Goodbye!")
        sys.exit(0)
