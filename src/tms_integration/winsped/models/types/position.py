from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, field_validator

from tms_integration.utils.config import get_all_valid_partner_ids


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
        valid_ids = get_all_valid_partner_ids()

        if value not in valid_ids:
            raise ValueError(
                f"Invalid partnerId: {value} not found in configured ID maps"
            )
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
