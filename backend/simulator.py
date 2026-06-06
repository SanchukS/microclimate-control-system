import random


class ClimateSimulator:
    WALL_LOSS_COEFF = 0.08
    HEATER_COEFF = 0.04
    COOLER_COEFF = 0.03
    AIRFLOW_GAIN = 1.5

    def __init__(self, inside_temp: float = 15.0) -> None:
        self.inside_temp = inside_temp

    def update_physics(
        self,
        heater_power: float,
        cooler_power: float,
        airflow_power: float,
        outside_temp: float,
    ) -> float:
        airflow_factor = 1.0 + self.AIRFLOW_GAIN * airflow_power / 100.0
        wall_exchange = (
            -self.WALL_LOSS_COEFF
            * (self.inside_temp - outside_temp)
            * airflow_factor
        )
        heating = self.HEATER_COEFF * heater_power
        cooling = self.COOLER_COEFF * cooler_power
        noise = random.uniform(-0.15, 0.15)

        self.inside_temp += wall_exchange + heating - cooling + noise
        return self.inside_temp


class SplitRangePIDController:
    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        deadband: float = 0.5,
    ) -> None:
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.deadband = deadband
        self._integral = 0.0
        self._prev_error: float | None = None

    def calculate(
        self,
        target_temp: float,
        current_temp: float,
        outside_temp: float,
        dt: float = 1.0,
    ) -> tuple[float, float, float]:
        error = target_temp - current_temp
        in_deadband = abs(error) <= self.deadband

        if not in_deadband:
            self._integral += error * dt

        if self._prev_error is None:
            derivative = 0.0
        else:
            derivative = (error - self._prev_error) / dt
        self._prev_error = error

        u_base = (target_temp - outside_temp) * 1.5
        u_pid = self.kp * error + self.ki * self._integral + self.kd * derivative
        u_total = max(-100.0, min(100.0, u_base + u_pid))

        if in_deadband:
            u_total = 0.0
            airflow_power = 0.0
        else:
            airflow_power = 50.0

        if u_total > 0:
            heater_power = u_total * 0.5
            cooler_power = 0.0
        elif u_total < 0:
            heater_power = 0.0
            cooler_power = abs(u_total) * 1.0
        else:
            heater_power = 0.0
            cooler_power = 0.0

        return heater_power, cooler_power, airflow_power
