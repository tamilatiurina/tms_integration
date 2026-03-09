from datetime import datetime, time

from pydantic import BaseModel

from src.tms_integration.winsped.models.types import *
from src.tms_integration.winsped.models.types.driver import Driver


class LisIn(BaseModel):
    records: list[RecordTypes] = []

    def validate_records(self):
        raise NotImplementedError

    @staticmethod
    def model_to_line(model):
        PREFIXED_FIELDS = {
            "posBreite": "PosBreite",
            "posLaenge": "PosLaenge",
            "driverCard1": "DriverCard1",
            "currentActivity": "DTCOCurrentActivity",
            "currentActivityStart": "DTCOCurrentActivityStart",
            "currentDriveMin": "DTCOCurrentDriveMin",
            "nextBreakStart": "DTCONextBreakStart",
            "nextBreakRemainMin": "DTCONextBreakRemainMin",
            "driverDayStart": "DTCODriverDayStart",
            "dayDriveRemainMin": "DTCODriverDayDriveRemainMin",
            "dayDriveMin": "DTCODayDriveMin",
            "dayWorkMin": "DTCODayWorkMin",
            "dayWorkRemainMin": "DTCODayWorkRemainMin",
            "dayWorkEnd": "DTCODayWorkEnd",
            "weekDriveMin": "DTCOWeekDriveMin",
            "weekDriveRemainMin": "DTCOWeekDriveRemainMin",
            "weekWorkMin": "DTCOWeekWorkMin",
            "weekWorkRemainMin": "DTCOWeekWorkRemainMin",
            "driverWeekStart": "DTCODriverWeekStart",
            "driverWeekDriveMin": "DTCODriverWeekDriveMin",
            "doubleWeekDriveMin": "DTCODoubleWeekDriveMin",
            "doubleWeekDriveRemainMin": "DTCODoubleWeekDriveRemainMin",
            "lastWeekRestMin": "DTCOLastWeekRestMin",
        }
        fields = []
        for field_key in model.__fields__.keys():
            field_value = model.dict().get(field_key)
            if isinstance(field_value, datetime):
                if field_value.time() == time(0, 0, 0):
                    field_value = field_value.strftime("%Y%m%d")
                else:
                    field_value = field_value.strftime("%Y%m%d %H%M%S")
            elif isinstance(field_value, time):
                field_value = field_value.strftime("%H%M")

            if field_key in PREFIXED_FIELDS:
                fields.append(
                    f"{PREFIXED_FIELDS[field_key]}={field_value if field_value is not None else ''}"
                )
            else:
                fields.append(str(field_value) if field_value is not None else "")

        return "|".join(fields)

    def generate_txt(self) -> str:
        self.validate_records()
        lines = []
        for record in self.records:
            lines.append(self.model_to_line(record))
        return "\n".join(lines)


class LisInPosition(LisIn):
    mandatory_records_type: list = [Position]

    def validate_records(self):
        records_type = {type(r) for r in self.records}
        types_missing = set(self.mandatory_records_type) - records_type
        if types_missing:
            raise ValueError(f"Some mandatory types are missing: {types_missing}")


class LisInDriver(LisIn):
    mandatory_records_type: list = [Driver]

    def validate_records(self):
        records_type = {type(r) for r in self.records}
        types_missing = set(self.mandatory_records_type) - records_type
        if types_missing:
            raise ValueError(f"Some mandatory types are missing: {types_missing}")
