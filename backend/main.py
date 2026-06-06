import asyncio
import math
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from database import SessionLocal, TelemetryLog, WorkShift, get_db, init_db
from schemas import PowerLevel, WorkShiftCreate, WorkShiftRead, TelemetryLogRead
from simulator import ClimateSimulator, SplitRangePIDController

ECO_TARGET_TEMP = 10.0
SIMULATION_INTERVAL_SEC = 2.0

simulator = ClimateSimulator(inside_temp=15.0)
pid = SplitRangePIDController(kp=4.0, ki=0.1, kd=1.0, deadband=0.5)
is_manual_mode = False
manual_heater = 0.0
manual_cooler = 0.0
manual_airflow = 0.0
current_target_temp = ECO_TARGET_TEMP
outside_temp = 5.0
heater_pwr = 0.0
cooler_pwr = 0.0
airflow_pwr = 0.0


class ManualControlRequest(BaseModel):
    heater: PowerLevel
    cooler: PowerLevel
    airflow: PowerLevel


class SystemStatus(BaseModel):
    inside_temp: float
    outside_temp: float
    target_temp: float
    heater_power: float
    cooler_power: float
    airflow_power: float
    is_manual_mode: bool


def _time_to_minutes(hhmm: str) -> int:
    hours, minutes = map(int, hhmm.split(":"))
    return hours * 60 + minutes


def _is_shift_active(now_min: int, start_min: int, end_min: int) -> bool:
    if start_min <= end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min


def _minutes_until_shift_start(now_min: int, start_min: int) -> int:
    if now_min <= start_min:
        return start_min - now_min
    return (24 * 60 - now_min) + start_min


def _resolve_target_temp(db: Session) -> float:
    now_min = datetime.now().hour * 60 + datetime.now().minute
    shifts = db.scalars(select(WorkShift)).all()

    active_target: float | None = None
    preheat_target: float | None = None
    nearest_preheat_minutes = 60

    for shift in shifts:
        start_min = _time_to_minutes(shift.start_time)
        end_min = _time_to_minutes(shift.end_time)

        if _is_shift_active(now_min, start_min, end_min):
            active_target = shift.target_temp
            break

        until_start = _minutes_until_shift_start(now_min, start_min)
        if until_start < nearest_preheat_minutes:
            nearest_preheat_minutes = until_start
            preheat_target = shift.target_temp

    if active_target is not None:
        return active_target
    if preheat_target is not None and nearest_preheat_minutes < 60:
        return preheat_target
    return ECO_TARGET_TEMP


async def simulation_loop() -> None:
    global outside_temp, current_target_temp
    global heater_pwr, cooler_pwr, airflow_pwr

    while True:
        outside_temp = 5.0 + 5.0 * math.sin(time.time() / 3600.0)

        db = SessionLocal()
        try:
            current_target_temp = _resolve_target_temp(db)

            if is_manual_mode:
                heater_pwr = manual_heater
                cooler_pwr = manual_cooler
                airflow_pwr = manual_airflow
            else:
                heater_pwr, cooler_pwr, airflow_pwr = pid.calculate(
                    current_target_temp,
                    simulator.inside_temp,
                    outside_temp,
                    dt=SIMULATION_INTERVAL_SEC,
                )

            simulator.update_physics(
                heater_pwr, cooler_pwr, airflow_pwr, outside_temp
            )

            db.add(
                TelemetryLog(
                    inside_temp=simulator.inside_temp,
                    outside_temp=outside_temp,
                    target_temp=current_target_temp,
                    heater_power=heater_pwr,
                    cooler_power=cooler_pwr,
                    airflow_power=airflow_pwr,
                    is_manual_mode=is_manual_mode,
                )
            )
            db.commit()
        finally:
            db.close()

        await asyncio.sleep(SIMULATION_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = asyncio.create_task(simulation_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Microclimate Control System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _current_status() -> SystemStatus:
    return SystemStatus(
        inside_temp=simulator.inside_temp,
        outside_temp=outside_temp,
        target_temp=current_target_temp,
        heater_power=heater_pwr,
        cooler_power=cooler_pwr,
        airflow_power=airflow_pwr,
        is_manual_mode=is_manual_mode,
    )


@app.get("/api/status", response_model=SystemStatus)
def get_status() -> SystemStatus:
    return _current_status()


@app.get("/api/history", response_model=list[TelemetryLogRead])
def get_history(db: Session = Depends(get_db)) -> list[TelemetryLogRead]:
    logs = db.scalars(
        select(TelemetryLog)
        .order_by(desc(TelemetryLog.timestamp))
        .limit(50)
    ).all()
    return [TelemetryLogRead.model_validate(log) for log in logs]


@app.post("/api/manual", response_model=SystemStatus)
def set_manual_mode(body: ManualControlRequest) -> SystemStatus:
    global is_manual_mode, manual_heater, manual_cooler, manual_airflow

    is_manual_mode = True
    manual_heater = body.heater
    manual_cooler = body.cooler
    manual_airflow = body.airflow
    return _current_status()


@app.post("/api/auto", response_model=SystemStatus)
def set_auto_mode() -> SystemStatus:
    global is_manual_mode

    is_manual_mode = False
    return _current_status()


@app.get("/api/shifts", response_model=list[WorkShiftRead])
def list_shifts(db: Session = Depends(get_db)) -> list[WorkShiftRead]:
    shifts = db.scalars(select(WorkShift).order_by(WorkShift.start_time)).all()
    return [WorkShiftRead.model_validate(shift) for shift in shifts]


@app.get("/api/shifts/{shift_id}", response_model=WorkShiftRead)
def get_shift(shift_id: int, db: Session = Depends(get_db)) -> WorkShiftRead:
    shift = db.get(WorkShift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Work shift not found")
    return WorkShiftRead.model_validate(shift)


@app.post("/api/shifts", response_model=WorkShiftRead, status_code=201)
def create_shift(
    body: WorkShiftCreate, db: Session = Depends(get_db)
) -> WorkShiftRead:
    shift = WorkShift(**body.model_dump())
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return WorkShiftRead.model_validate(shift)


@app.put("/api/shifts/{shift_id}", response_model=WorkShiftRead)
def update_shift(
    shift_id: int, body: WorkShiftCreate, db: Session = Depends(get_db)
) -> WorkShiftRead:
    shift = db.get(WorkShift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Work shift not found")

    for field, value in body.model_dump().items():
        setattr(shift, field, value)

    db.commit()
    db.refresh(shift)
    return WorkShiftRead.model_validate(shift)


@app.delete("/api/shifts/{shift_id}", status_code=204)
def delete_shift(shift_id: int, db: Session = Depends(get_db)) -> None:
    shift = db.get(WorkShift, shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail="Work shift not found")

    db.delete(shift)
    db.commit()
