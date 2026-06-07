from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PowerLevel = Annotated[float, Field(ge=0.0, le=100.0)]
TimeHHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
SystemState = Literal["STANDBY", "SAFETY_CORRECTION", "PRE_START", "WORK_SHIFT"]


class TelemetryLogCreate(BaseModel):
    inside_temp: float
    outside_temp: float
    inflow_temp: float
    heater_temp: float
    cooler_temp: float
    target_temp: float
    heater_power: PowerLevel
    cooler_power: PowerLevel
    airflow_power: PowerLevel
    dampers_open: bool
    is_manual_mode: bool
    current_state: SystemState
    t_pre_start: float


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
