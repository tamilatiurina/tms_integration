import logging

from src.tms_integration.tracker_manager import MultiAPITracker
from src.tms_integration.utils.config import (
    get_lis_winsped,
    get_tracker_config,
    validate_config,
)
from src.tms_integration.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

def main():
    """Main entry point"""
    try:
        setup_logging(level=logging.INFO)
        validate_config()
        logger.info("Configuration validated")

        lis_winsped = get_lis_winsped()
        logger.info("LisWinSped initialized")

        multi_tracker = MultiAPITracker(lis_winsped=lis_winsped)

        for tracker_info in get_tracker_config():
            if tracker_info["type"] == "position":
                multi_tracker.add_position_tracker(api_key=tracker_info["api_key"],
                                                   api_name=tracker_info["api_name"],
                                                   report_interval=10)
            elif tracker_info["type"] == "driver":
                multi_tracker.add_driver_tracker(api_key=tracker_info["api_key"],
                                                 api_name=tracker_info["api_name"],
                                                 drivers_ids_path=tracker_info["drivers_path"],
                                                 report_interval=10)

        logger.info(f"Starting {len(multi_tracker.trackers)} trackers")
        multi_tracker.start_all()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
