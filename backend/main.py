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
from schemas import PowerLevel, SystemState, WorkShiftCreate, WorkShiftRead, TelemetryLogRead
from simulator import CascadedClimateController, ClimateSimulator

# --- Параметры системы ---
T_safe_min = 12.0
T_safe_max = 28.0
T_safe_hyst = 2.0
T_inflow_min = 16.0
T_inflow_max = 40.0
T_heater_safe = 45.0
T_cooler_safe = 15.0
T_purge_diff = 3.0
t_purge_max_heat = 300.0
t_purge_max_cool = 600.0
F_min = 20.0
Kp = 4.0
Ki = 0.1
Kd = 1.0
K_fan = 5.0
K_H = 0.5
K_C = 0.5
t_dwell = 60.0
deadband = 0.5
fan_trigger = 5.0
SAFE_START_DURATION_SEC = 10.0
SIMULATION_INTERVAL_SEC = 2.0

# --- Глобальное состояние ---
simulator = ClimateSimulator(inside_temp=15.0)
controller = CascadedClimateController(
    kp=Kp,
    ki=Ki,
    k_fan=K_fan,
    k_h=K_H,
    k_c=K_C,
    deadband=deadband,
    fan_trigger=fan_trigger,
    inflow_min=T_inflow_min,
    inflow_max=T_inflow_max,
    t_dwell=t_dwell,
    f_min=F_min,
)

current_state: SystemState = "STANDBY"
t_pre_start = 120.0
v_smooth = 0.1
alpha = 0.2
pre_start_timer = 0.0
pre_start_temp_start = 15.0
purge_timer = 0.0
is_purging = False
prev_inflow_setpoint = 15.0
safe_start_timer = 0.0
is_safe_starting = False

is_manual_mode = False
manual_heater = 0.0
manual_cooler = 0.0
manual_airflow = 0.0

current_target_temp = 15.0
safety_target_temp = T_safe_min + T_safe_hyst
safety_heating = True

outside_temp = 5.0
heater_pwr = 0.0
cooler_pwr = 0.0
airflow_pwr = 0.0
dampers_open = False


class ManualControlRequest(BaseModel):
    heater: PowerLevel
    cooler: PowerLevel
    airflow: PowerLevel


class SystemStatus(BaseModel):
    inside_temp: float
    outside_temp: float
    inflow_temp: float
    heater_temp: float
    cooler_temp: float
    target_temp: float
    heater_power: float
    cooler_power: float
    airflow_power: float
    dampers_open: bool
    is_manual_mode: bool
    current_state: SystemState
    t_pre_start: float


def _time_to_minutes(hhmm: str) -> int:
    hours, minutes = map(int, hhmm.split(":"))
    return hours * 60 + minutes


def _now_minutes() -> int:
    now = datetime.now()
    return now.hour * 60 + now.minute


def _is_shift_active(now_min: int, start_min: int, end_min: int) -> bool:
    if start_min <= end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min


def _minutes_until_shift_start(now_min: int, start_min: int) -> int:
    if now_min <= start_min:
        return start_min - now_min
    return (24 * 60 - now_min) + start_min


def _get_all_shifts(db: Session) -> list[WorkShift]:
    return list(db.scalars(select(WorkShift).order_by(WorkShift.start_time)).all())


def _get_active_shift(db: Session, now_min: int) -> WorkShift | None:
    for shift in _get_all_shifts(db):
        start_min = _time_to_minutes(shift.start_time)
        end_min = _time_to_minutes(shift.end_time)
        if _is_shift_active(now_min, start_min, end_min):
            return shift
    return None


def _get_nearest_upcoming_shift(
    db: Session, now_min: int
) -> tuple[WorkShift, int] | None:
    nearest_shift: WorkShift | None = None
    nearest_minutes = 24 * 60 + 1

    for shift in _get_all_shifts(db):
        start_min = _time_to_minutes(shift.start_time)
        until_start = _minutes_until_shift_start(now_min, start_min)
        if until_start < nearest_minutes:
            nearest_minutes = until_start
            nearest_shift = shift

    if nearest_shift is None:
        return None
    return nearest_shift, nearest_minutes


def _compute_adaptive_pre_start(next_target: float, inside_temp: float) -> float:
    global t_pre_start
    t_pre_start = abs(next_target - inside_temp) / v_smooth + 15.0
    t_pre_start = max(15.0, min(240.0, t_pre_start))
    return t_pre_start


def _enter_state(new_state: SystemState) -> None:
    global current_state, is_safe_starting, safe_start_timer

    if new_state == current_state:
        return

    if new_state in ("SAFETY_CORRECTION", "PRE_START"):
        is_safe_starting = True
        safe_start_timer = 0.0

    current_state = new_state


def _activate_purge() -> None:
    global is_purging, purge_timer

    is_purging = True
    purge_timer = 0.0


def _tick_safe_start() -> bool:
    """Возвращает True, если безопасный пуск ещё активен (контроллер отключён)."""
    global safe_start_timer, is_safe_starting

    if not is_safe_starting:
        return False

    safe_start_timer += SIMULATION_INTERVAL_SEC
    if safe_start_timer >= SAFE_START_DURATION_SEC:
        is_safe_starting = False
        return False
    return True


def _apply_safe_start_outputs() -> None:
    global heater_pwr, cooler_pwr, airflow_pwr, dampers_open

    dampers_open = True
    heater_pwr = 0.0
    cooler_pwr = 0.0
    airflow_pwr = F_min


def _apply_controller(target_temp: float, current_time: float) -> None:
    global heater_pwr, cooler_pwr, airflow_pwr, dampers_open, prev_inflow_setpoint

    output = controller.calculate(
        target_temp,
        simulator.inside_temp,
        outside_temp,
        simulator.inflow_temp,
        current_time,
        heater_pwr,
        cooler_pwr,
        dt=SIMULATION_INTERVAL_SEC,
    )
    heater_pwr = output["heater_power"]
    cooler_pwr = output["cooler_power"]
    airflow_pwr = output["airflow_power"]
    prev_inflow_setpoint = output["inflow_setpoint"]
    dampers_open = True


def _process_purge() -> None:
    global is_purging, purge_timer, heater_pwr, cooler_pwr, airflow_pwr, dampers_open

    heater_pwr = 0.0
    cooler_pwr = 0.0
    dampers_open = True
    airflow_pwr = 30.0
    purge_timer += SIMULATION_INTERVAL_SEC

    heating_purge = prev_inflow_setpoint >= outside_temp
    purge_complete = False

    if heating_purge:
        purge_complete = (
            simulator.heater_temp < T_heater_safe
            or abs(simulator.heater_temp - outside_temp) < T_purge_diff
            or purge_timer >= t_purge_max_heat
        )
    else:
        purge_complete = (
            simulator.cooler_temp > T_cooler_safe
            or abs(simulator.cooler_temp - outside_temp) < T_purge_diff
            or purge_timer >= t_purge_max_cool
        )

    if purge_complete:
        is_purging = False
        heater_pwr = 0.0
        cooler_pwr = 0.0
        airflow_pwr = 0.0
        dampers_open = False
        _enter_state("STANDBY")


def _run_standby_logic(db: Session, now_min: int) -> None:
    global current_target_temp, pre_start_temp_start, pre_start_timer
    global safety_target_temp, safety_heating
    global heater_pwr, cooler_pwr, airflow_pwr, dampers_open

    heater_pwr = 0.0
    cooler_pwr = 0.0
    airflow_pwr = 0.0
    dampers_open = False

    inside = simulator.inside_temp

    if inside < T_safe_min:
        safety_target_temp = T_safe_min + T_safe_hyst
        safety_heating = True
        current_target_temp = safety_target_temp
        _enter_state("SAFETY_CORRECTION")
        return

    if inside > T_safe_max:
        safety_target_temp = T_safe_max - T_safe_hyst
        safety_heating = False
        current_target_temp = safety_target_temp
        _enter_state("SAFETY_CORRECTION")
        return

    upcoming = _get_nearest_upcoming_shift(db, now_min)
    if upcoming is not None:
        shift, minutes_until = upcoming
        _compute_adaptive_pre_start(shift.target_temp, inside)
        current_target_temp = shift.target_temp

        if minutes_until <= t_pre_start:
            pre_start_temp_start = inside
            pre_start_timer = 0.0
            current_target_temp = shift.target_temp
            _enter_state("PRE_START")
    else:
        current_target_temp = inside


def _run_safety_correction_logic(current_time: float) -> None:
    global current_target_temp

    if _tick_safe_start():
        _apply_safe_start_outputs()
        return

    _apply_controller(safety_target_temp, current_time)

    inside = simulator.inside_temp
    corrected = (
        safety_heating and inside >= safety_target_temp
    ) or (
        not safety_heating and inside <= safety_target_temp
    )

    if corrected:
        _activate_purge()
        _enter_state("STANDBY")


def _run_pre_start_logic(db: Session, now_min: int, current_time: float) -> None:
    global pre_start_timer, v_smooth, current_target_temp

    upcoming = _get_nearest_upcoming_shift(db, now_min)
    if upcoming is not None:
        shift, _ = upcoming
        current_target_temp = shift.target_temp

    if _tick_safe_start():
        _apply_safe_start_outputs()
    else:
        _apply_controller(current_target_temp, current_time)

    pre_start_timer += SIMULATION_INTERVAL_SEC

    active_shift = _get_active_shift(db, now_min)
    if active_shift is not None:
        delta_t_fact = pre_start_timer / 60.0
        delta_temp = abs(active_shift.target_temp - pre_start_temp_start)
        v_climate = delta_temp / max(1.0, delta_t_fact)
        v_smooth = alpha * v_climate + (1.0 - alpha) * v_smooth
        current_target_temp = active_shift.target_temp
        _enter_state("WORK_SHIFT")


def _run_work_shift_logic(db: Session, now_min: int, current_time: float) -> None:
    global current_target_temp

    active_shift = _get_active_shift(db, now_min)
    if active_shift is None:
        _activate_purge()
        _enter_state("STANDBY")
        return

    current_target_temp = active_shift.target_temp

    if _tick_safe_start():
        _apply_safe_start_outputs()
    else:
        _apply_controller(current_target_temp, current_time)


def _run_automatic_control(db: Session) -> None:
    now_min = _now_minutes()
    current_time = time.time()

    if is_purging:
        _process_purge()
        return

    if current_state == "STANDBY":
        _run_standby_logic(db, now_min)
    elif current_state == "SAFETY_CORRECTION":
        _run_safety_correction_logic(current_time)
    elif current_state == "PRE_START":
        _run_pre_start_logic(db, now_min, current_time)
    elif current_state == "WORK_SHIFT":
        _run_work_shift_logic(db, now_min, current_time)


async def simulation_loop() -> None:
    global outside_temp, heater_pwr, cooler_pwr, airflow_pwr, dampers_open

    while True:
        outside_temp = 5.0 + 5.0 * math.sin(time.time() / 3600.0)

        db = SessionLocal()
        try:
            if is_manual_mode:
                heater_pwr = manual_heater
                cooler_pwr = manual_cooler
                airflow_pwr = manual_airflow
                dampers_open = manual_airflow > 0.0
            else:
                _run_automatic_control(db)

            simulator.update_physics(
                heater_pwr,
                cooler_pwr,
                airflow_pwr,
                dampers_open,
                outside_temp,
                dt=SIMULATION_INTERVAL_SEC,
            )

            db.add(
                TelemetryLog(
                    inside_temp=simulator.inside_temp,
                    outside_temp=outside_temp,
                    inflow_temp=simulator.inflow_temp,
                    heater_temp=simulator.heater_temp,
                    cooler_temp=simulator.cooler_temp,
                    target_temp=current_target_temp,
                    heater_power=heater_pwr,
                    cooler_power=cooler_pwr,
                    airflow_power=airflow_pwr,
                    dampers_open=dampers_open,
                    is_manual_mode=is_manual_mode,
                    current_state=current_state,
                    t_pre_start=t_pre_start,
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
        inflow_temp=simulator.inflow_temp,
        heater_temp=simulator.heater_temp,
        cooler_temp=simulator.cooler_temp,
        target_temp=current_target_temp,
        heater_power=heater_pwr,
        cooler_power=cooler_pwr,
        airflow_power=airflow_pwr,
        dampers_open=dampers_open,
        is_manual_mode=is_manual_mode,
        current_state=current_state,
        t_pre_start=t_pre_start,
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
