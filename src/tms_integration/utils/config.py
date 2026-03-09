import os
from typing import Any

from dotenv import load_dotenv

from tms_integration.utils import FtpConfig
from tms_integration.winsped import LisWinSped

load_dotenv()


def get_ftp_config() -> FtpConfig:
    """Get FTP configuration from environment variables"""
    return FtpConfig(
        host=os.getenv("FTP_HOST"),
        port=os.getenv("FTP_PORT"),
        username=os.getenv("FTP_USERNAME"),
        password=os.getenv("FTP_PASSWORD"),
        timeout=int(os.getenv("FTP_TIMEOUT", 30)),
    )


def get_lis_winsped() -> LisWinSped:
    """
    Get initialized LisWinSped instance

    This centralizes all WinSped configuration in one place.
    Call this once in main.py and pass it around.

    Returns:
        LisWinSped: Configured instance ready to use

    Example:
        # In main.py
        from config import get_lis_winsped

        lis_winsped = get_lis_winsped()
        multi_tracker = MultiAPITracker(lis_winsped=lis_winsped)
    """
    return LisWinSped(
        config=get_ftp_config(),
        import_dest_folder=os.getenv("FTP_IMPORT_FOLDER"),
    )

def get_tracker_config() -> list[dict[str, Any]]:
    """Return all tracker configurations"""
    config = []

    for env_key, api_name in [("API_KEY_UA", "POS_UA"), ("API_KEY_PL", "POS_PL")]:
        api_key = os.getenv(env_key)
        if api_key:
            config.append(
                {
                    "type": "position",
                    "api_key": api_key,
                    "api_name": api_name,
                }
            )

    for api_key_env, api_name, path_env in [
        ("API_KEY_UA", "DR_UA", "DRIVER_ID_PATH_UA"),
        ("API_KEY_PL", "DR_PL", "DRIVER_ID_PATH_PL"),
    ]:
        api_key = os.getenv(api_key_env)
        drivers_path = os.getenv(path_env)

        if api_key and drivers_path:
            config.append(
                {
                    "type": "driver",
                    "api_key": api_key,
                    "api_name": api_name,
                    "drivers_path": drivers_path,
                }
            )

    return config

def validate_config() -> bool:
    """Validate all required environment variables"""
    required_env_vars = [
        "FTP_HOST",
        "FTP_PORT"
        "FTP_USERNAME",
        "FTP_PASSWORD",
        "FTP_IMPORT_FOLDER",
        "API_KEY_UA",
        "API_KEY_PL",
        "DRIVER_ID_PATH_UA",
        "DRIVER_ID_PATH_PL",
    ]

    missing = [var for var in required_env_vars if not os.getenv(var)]

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Please check your .env file"
        )

    return True
