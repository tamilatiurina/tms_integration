import json
import os
from datetime import datetime, time
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

load_dotenv()


def load_id_map(env_var: str) -> dict:
    path = os.getenv(env_var)
    if not path:
        raise ValueError(f"{env_var} not set in environment")
    with open(path) as f:
        return json.load(f)


VALID_PARTNER_IDS_UA = load_id_map("VEHICLE_ID_UA_MAP_PATH")
VALID_PARTNER_IDS_PL = load_id_map("VEHICLE_ID_PL_MAP_PATH")


class Position(BaseModel):
    messageNumber: Literal["15"] = "15"
    positionDate: datetime
    positionTime: time
    partnerId: str
    messageId: Literal["0"] = "0"
    posBreite: str
    posLaenge: str

    @field_validator("positionDate", mode="before")
    @staticmethod
    def parse_date(value):
        if isinstance(value, str):
            return datetime.strptime(value, "%Y%m%d")
        return value

    @field_validator("positionTime", mode="before")
    @staticmethod
    def parse_time(value):
        if isinstance(value, str):
            return datetime.strptime(value, "%H%M%S").time()
        return value

    @field_validator("partnerId", mode="before")
    @staticmethod
    def validate_partnerId(value):
        if value not in VALID_PARTNER_IDS_UA and value not in VALID_PARTNER_IDS_PL:
            raise ValueError(f"Invalid partnerId: {value} not found in id map")
        return value

    @field_validator("posBreite", mode="before")
    @staticmethod
    def validate_posBreite(value):
        coord = float(value)

        direction = "N" if coord >= 0 else "S"
        coord = abs(coord)

        # split into degrees and decimals
        degrees = int(coord)
        decimals = int(round((coord - degrees) * 10000))

        # Format: GGG = 3-digit degrees, NNNN = 4-digit decimals
        # Example: 52.2735 -> degrees=52, decimals=2735 -> "0522735N"
        formatted = f"{degrees:03d}{decimals:04d}{direction}"

        return formatted

    @field_validator("posLaenge", mode="before")
    @staticmethod
    def validate_posLaenge(value):
        coord = float(value)

        direction = "E" if coord >= 0 else "W"
        coord = abs(coord)

        # split into degrees and decimals
        degrees = int(coord)
        decimals = int(round((coord - degrees) * 10000))

        # Format: GGG = 3-digit degrees, NNNN = 4-digit decimals
        # Example: 52.2735 -> degrees=52, decimals=2735 -> "0522735E"
        formatted = f"{degrees:03d}{decimals:04d}{direction}"

        return formatted
