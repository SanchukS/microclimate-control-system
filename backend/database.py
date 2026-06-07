from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./climate.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
    )
    inside_temp: Mapped[float] = mapped_column(Float)
    outside_temp: Mapped[float] = mapped_column(Float)
    inflow_temp: Mapped[float] = mapped_column(Float)
    heater_temp: Mapped[float] = mapped_column(Float)
    cooler_temp: Mapped[float] = mapped_column(Float)
    target_temp: Mapped[float] = mapped_column(Float)
    heater_power: Mapped[float] = mapped_column(Float)
    cooler_power: Mapped[float] = mapped_column(Float)
    airflow_power: Mapped[float] = mapped_column(Float)
    dampers_open: Mapped[bool] = mapped_column(Boolean)
    is_manual_mode: Mapped[bool] = mapped_column(Boolean)
    current_state: Mapped[str] = mapped_column(String(30))
    t_pre_start: Mapped[float] = mapped_column(Float)


class WorkShift(Base):
    __tablename__ = "work_shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    target_temp: Mapped[float] = mapped_column(Float)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
