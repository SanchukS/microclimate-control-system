import random


def _sign(value: float) -> float:
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0


class ClimateSimulator:
    def __init__(self, inside_temp: float = 15.0) -> None:
        self.inside_temp = inside_temp
        self.heater_temp = 15.0
        self.cooler_temp = 15.0
        self.inflow_temp = 15.0

    def update_physics(
        self,
        heater_pwr: float,
        cooler_pwr: float,
        airflow_pwr: float,
        dampers_open: bool,
        outside_temp: float,
        dt: float = 2.0,
    ) -> tuple[float, float, float, float]:
        if heater_pwr > 0:
            self.heater_temp += 0.25 * heater_pwr * dt
        self.heater_temp -= (
            (self.heater_temp - self.inside_temp)
            * (0.002 + 0.004 * airflow_pwr / 100.0)
            * dt
        )
        self.heater_temp = max(self.heater_temp, self.inside_temp)

        if cooler_pwr > 0:
            self.cooler_temp -= 0.2 * cooler_pwr * dt
        self.cooler_temp += (
            (self.inside_temp - self.cooler_temp)
            * (0.002 + 0.004 * airflow_pwr / 100.0)
            * dt
        )
        self.cooler_temp = min(self.cooler_temp, self.inside_temp)

        if not dampers_open or airflow_pwr == 0:
            self.inflow_temp = self.inside_temp
        elif heater_pwr > 0:
            self.inflow_temp = outside_temp + (
                (self.heater_temp - outside_temp) * 0.008 * airflow_pwr * dt
            )
            self.inflow_temp = min(self.inflow_temp, self.heater_temp)
        elif cooler_pwr > 0:
            self.inflow_temp = outside_temp - (
                (outside_temp - self.cooler_temp) * 0.008 * airflow_pwr * dt
            )
            self.inflow_temp = max(self.inflow_temp, self.cooler_temp)
        else:
            self.inflow_temp = outside_temp

        self.inside_temp += (outside_temp - self.inside_temp) * 0.0005 * dt
        if dampers_open:
            self.inside_temp += (
                (self.inflow_temp - self.inside_temp) * 0.0008 * airflow_pwr * dt
            )
        self.inside_temp += random.uniform(-0.1, 0.1)

        return (
            self.inside_temp,
            self.inflow_temp,
            self.heater_temp,
            self.cooler_temp,
        )


class CascadedClimateController:
    def __init__(
        self,
        kp: float,
        ki: float,
        k_fan: float,
        k_h: float,
        k_c: float,
        deadband: float,
        fan_trigger: float,
        inflow_min: float,
        inflow_max: float,
        t_dwell: float,
        f_min: float,
    ) -> None:
        self.kp = kp
        self.ki = ki
        self.k_fan = k_fan
        self.k_h = k_h
        self.k_c = k_c
        self.deadband = deadband
        self.fan_trigger = fan_trigger
        self.inflow_min = inflow_min
        self.inflow_max = inflow_max
        self.t_dwell = t_dwell
        self.f_min = f_min

        self.integral = 0.0
        self.prev_error = 0.0
        self.last_mode_switch_time = -1e9
        self.current_active_mode = "HEATING"
        self.last_inflow_setpoint = (inflow_min + inflow_max) / 2.0
        self.last_airflow_power = f_min

    def reset_integrator(self) -> None:
        self.integral = 0.0

    def calculate(
        self,
        target_temp: float,
        current_temp: float,
        outside_temp: float,
        current_inflow_temp: float,
        current_time: float,
        last_heater: float,
        last_cooler: float,
        dt: float = 2.0,
    ) -> dict[str, float]:
        error = target_temp - current_temp
        if abs(error) <= self.deadband:
            error = 0.0

        new_integral = self.integral + self.ki * error * dt

        saturated_heating = (
            (
                self.last_inflow_setpoint >= self.inflow_max
                or last_heater >= 100.0
            )
            and self.last_airflow_power >= 100.0
            and error > 0
        )
        saturated_cooling = (
            (
                self.last_inflow_setpoint <= self.inflow_min
                or last_cooler >= 100.0
            )
            and self.last_airflow_power >= 100.0
            and error < 0
        )

        if not saturated_heating and not saturated_cooling:
            self.integral = new_integral

        t_pid = self.kp * error + self.integral
        self.prev_error = error

        sign_t_pid = _sign(t_pid)
        t_inflow_calc = target_temp + sign_t_pid * min(abs(t_pid), self.fan_trigger)
        t_inflow_setpoint = max(
            self.inflow_min, min(t_inflow_calc, self.inflow_max)
        )
        unfulfilled = abs(t_inflow_calc - t_inflow_setpoint)
        t_boost = max(0.0, abs(t_pid) - self.fan_trigger)
        t_fan_active = t_boost + unfulfilled

        if t_fan_active == 0.0:
            airflow_power = self.f_min
        else:
            airflow_power = min(100.0, self.f_min + self.k_fan * t_fan_active)

        e_inflow = t_inflow_setpoint - current_inflow_temp
        required_mode = (
            "HEATING" if t_inflow_setpoint >= outside_temp else "COOLING"
        )

        if required_mode != self.current_active_mode:
            if current_time - self.last_mode_switch_time > self.t_dwell:
                self.current_active_mode = required_mode
                self.last_mode_switch_time = current_time

        if self.current_active_mode == "HEATING":
            heater_power = max(0.0, min(100.0, last_heater + self.k_h * e_inflow))
            cooler_power = 0.0
        else:
            cooler_power = max(0.0, min(100.0, last_cooler - self.k_c * e_inflow))
            heater_power = 0.0

        self.last_inflow_setpoint = t_inflow_setpoint
        self.last_airflow_power = airflow_power

        return {
            "heater_power": heater_power,
            "cooler_power": cooler_power,
            "airflow_power": airflow_power,
            "inflow_setpoint": t_inflow_setpoint,
        }
