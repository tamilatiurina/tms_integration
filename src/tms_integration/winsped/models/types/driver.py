from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, field_validator, ConfigDict


class Driver(BaseModel):
    model_config = ConfigDict(
        validate_assignment=True,
        # Suppress serialization warnings
        ser_json_timedelta="float",
    )
    messageNumber: Literal["499"] = "499"
    stateDate: datetime
    stateTime: time
    vehicleType: Literal["LKW"] = "LKW"
    driverCard1: str  # DriverCard1=
    currentActivity: str  # DTCOCurrentActivity=
    currentActivityStart: datetime  # DTCOCurrentActivityStart=
    currentDriveMin: int  # DTCOCurrentDriveMin=
    nextBreakStart: datetime | None = None  # DTCONextBreakStart=
    nextBreakRemainMin: int | None = 0  # DTCONextBreakRemainMin=
    driverDayStart: datetime | None = None  # DTCODriverDayStart=
    dayDriveRemainMin: int  # DTCODriverDayDriveRemainMin=
    dayDriveMin: int  # DTCODayDriveMin=
    dayWorkMin: int  # DTCODayWorkMin=
    dayWorkRemainMin: int | None = 0  # DTCODayWorkRemainMin=
    dayWorkEnd: datetime | None = None  # DTCODayWorkEnd=
    weekDriveMin: int  # DTCOWeekDriveMin=
    weekDriveRemainMin: int  # DTCOWeekDriveRemainMin=
    weekWorkMin: int  # DTCOWeekWorkMin=
    weekWorkRemainMin: int | None = 0  # DTCOWeekWorkRemainMin=
    driverWeekStart: datetime | None = None  # DTCODriverWeekStart=
    driverWeekDriveMin: int  # DTCODriverWeekDriveMin=
    doubleWeekDriveMin: int  # DTCODoubleWeekDriveMin=
    doubleWeekDriveRemainMin: int  # DTCODoubleWeekDriveRemainMin=
    lastWeekRestMin: int  # DTCOLastWeekRestMin=

    @field_validator(
        "stateDate",
        "currentActivityStart",
        "nextBreakStart",
        "driverDayStart",
        "dayWorkEnd",
        "driverWeekStart",
        mode="before",
    )
    @staticmethod
    def parse_date(value):
        if isinstance(value, str):
            # handle both "20140128" and "20140128 005800" formats
            value = value.strip()
            if len(value) == 8:
                return datetime.strptime(value, "%Y%m%d")
            elif len(value) == 15:
                return datetime.strptime(value, "%Y%m%d %H%M%S")
        return value

    @field_validator("stateTime", mode="before")
    @staticmethod
    def parse_time(value):
        if isinstance(value, str):
            return datetime.strptime(value, "%H%M").time()
        return value

    @field_validator("currentActivity", mode="before")
    @staticmethod
    def parse_activity(value):
        activity_map = {
            "UNKNOWN": "Unknown",
            "DRIVING": "Drive",
            "WORKING": "Work",
            "RESTING": "Rest",
            "AVAILABLE": "Availability",
        }
        return activity_map.get(value.upper(), value)
