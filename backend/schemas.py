from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

PowerLevel = Annotated[float, Field(ge=0.0, le=100.0)]
TimeHHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class TelemetryLogCreate(BaseModel):
    inside_temp: float
    outside_temp: float
    target_temp: float
    heater_power: PowerLevel
    cooler_power: PowerLevel
    airflow_power: PowerLevel
    is_manual_mode: bool


class TelemetryLogRead(TelemetryLogCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime


class WorkShiftCreate(BaseModel):
    start_time: TimeHHMM
    end_time: TimeHHMM
    target_temp: float


class WorkShiftRead(WorkShiftCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
