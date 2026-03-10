import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.tms_integration.utils.ftp import FtpConfig

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


def get_lis_winsped():
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
    from src.tms_integration.winsped.winsped import LisWinSped
    return LisWinSped(
        config=get_ftp_config(),
        import_dest_folder=os.getenv("FTP_IMPORT_FOLDER"),
    )


def _load_id_map(env_var: str) -> dict:
    """
    Load ID map from JSON file specified in environment variable

    Args:
        env_var: Environment variable name containing path to JSON file

    Returns:
        dict: Parsed JSON content

    Raises:
        ValueError: If env var not set or file not found
    """
    relative_path = os.getenv(env_var)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    file_path = project_root / relative_path
    if not file_path:
        raise ValueError(f"{env_var} not set in environment")

    if not os.path.exists(file_path):
        raise ValueError(f"ID map file not found: {file_path}")

    try:
        with open(file_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")


VALID_PARTNER_IDS_UA = _load_id_map("VEHICLE_ID_MAP_PATH_UA")
VALID_PARTNER_IDS_PL = _load_id_map("VEHICLE_ID_MAP_PATH_PL")


def get_valid_partner_ids(country: str) -> dict:
    """
    Get valid partner IDs for a specific country

    Args:
        country: Country code ("UA" or "PL")

    Returns:
        dict: Valid partner IDs for that country

    Raises:
        ValueError: If country not supported
    """
    if country == "UA":
        return VALID_PARTNER_IDS_UA
    elif country == "PL":
        return VALID_PARTNER_IDS_PL
    else:
        raise ValueError(f"Unsupported country: {country}")


def get_all_valid_partner_ids() -> dict:
    """Get combined dictionary of all valid partner IDs from all countries"""
    combined = {}
    combined.update(VALID_PARTNER_IDS_UA)
    combined.update(VALID_PARTNER_IDS_PL)
    return combined


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
        drivers_path_relative = os.getenv(path_env)
        drivers_path = Path(__file__).resolve().parent.parent.parent.parent / drivers_path_relative
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
        "FTP_PORT",
        "FTP_USERNAME",
        "FTP_PASSWORD",
        "FTP_IMPORT_FOLDER",
        "API_KEY_UA",
        "API_KEY_PL",
        "DRIVER_ID_PATH_UA",
        "DRIVER_ID_PATH_PL",
        "VEHICLE_ID_MAP_PATH_UA",
        "VEHICLE_ID_MAP_PATH_PL"
    ]

    missing = [var for var in required_env_vars if not os.getenv(var)]

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Please check your .env file"
        )

    try:
        _load_id_map("VEHICLE_ID_MAP_PATH_UA")
        _load_id_map("VEHICLE_ID_MAP_PATH_PL")
    except ValueError as e:
        raise ValueError(f"ID map validation failed: {e}")

    return True
