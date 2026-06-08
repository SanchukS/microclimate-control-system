import math
import random


def _sign(value: float) -> float:
    if value > 0:
        return 1.0
    if value < 0:
        return -1.0
    return 0.0


class ClimateSimulator:
    C_AIR = 1005.0
    G_MAX = 1.5
    C_ROOM_EFF = 5.0e7
    C_HEATER = 25000.0
    C_COOLER = 30000.0
    P_H_MAX = 40000.0
    P_C_MAX = 30000.0
    K_WALLS = 750.0
    K_PASSIVE_H = 15.0
    K_PASSIVE_C = 15.0
    K_ACTIVE_H = 1500.0
    K_ACTIVE_C = 1200.0
    K_SENSOR_LOSS = 0.005
    P_BASELINE = 1000.0
    P_MACH_I = 3000.0
    P_ON = 0.02
    P_OFF = 0.015

    def __init__(self, inside_temp: float = 15.0) -> None:
        self.inside_temp = inside_temp
        self.inflow_temp = 15.0
        self.heater_temp = 15.0
        self.cooler_temp = 15.0
        self.machine_states = [False] * 5
        self.P_internal = self.P_BASELINE
        self.prev_shift_active = False

    def _update_internal_heat(self, is_shift_active: bool, dt: float) -> None:
        if is_shift_active and not self.prev_shift_active:
            self.machine_states = [True, True, False, False, False]
        elif not is_shift_active:
            self.machine_states = [False] * 5
            self.P_internal = self.P_BASELINE
            self.prev_shift_active = is_shift_active
            return
        else:
            p_on_step = self.P_ON * (dt / 60.0)
            p_off_step = self.P_OFF * (dt / 60.0)
            for i in range(5):
                if not self.machine_states[i]:
                    if random.random() < p_on_step:
                        self.machine_states[i] = True
                elif random.random() < p_off_step:
                    self.machine_states[i] = False

        self.P_internal = self.P_BASELINE + sum(
            self.P_MACH_I for active in self.machine_states if active
        )
        self.prev_shift_active = is_shift_active

    def update_physics(
        self,
        heater_pwr: float,
        cooler_pwr: float,
        airflow_pwr: float,
        dampers_open: bool,
        outside_temp: float,
        is_shift_active: bool,
        dt: float = 2.0,
    ) -> tuple[float, float, float, float]:
        d_val = 1.0 if dampers_open else 0.0
        f_val = airflow_pwr / 100.0
        g_flow = d_val * f_val * self.G_MAX

        self._update_internal_heat(is_shift_active, dt)

        p_electric_h = (heater_pwr / 100.0) * self.P_H_MAX
        p_passive_loss_h = self.K_PASSIVE_H * (self.heater_temp - self.inside_temp)

        if g_flow > 0:
            ntu_h = self.K_ACTIVE_H / (g_flow * self.C_AIR)
            epsilon_h = 1.0 - math.exp(-ntu_h)
            t_after_heater = outside_temp + epsilon_h * (
                self.heater_temp - outside_temp
            )
            p_active_loss_h = g_flow * self.C_AIR * (t_after_heater - outside_temp)
        else:
            t_after_heater = outside_temp
            p_active_loss_h = 0.0

        d_t_heater = (
            p_electric_h - p_passive_loss_h - p_active_loss_h
        ) / self.C_HEATER
        self.heater_temp += dt * d_t_heater

        p_electric_c = (cooler_pwr / 100.0) * self.P_C_MAX
        p_passive_loss_c = self.K_PASSIVE_C * (self.inside_temp - self.cooler_temp)

        if g_flow > 0:
            ntu_c = self.K_ACTIVE_C / (g_flow * self.C_AIR)
            epsilon_c = 1.0 - math.exp(-ntu_c)
            self.inflow_temp = t_after_heater - epsilon_c * (
                t_after_heater - self.cooler_temp
            )
            p_active_loss_c = g_flow * self.C_AIR * (
                t_after_heater - self.inflow_temp
            )
        else:
            p_active_loss_c = 0.0
            self.inflow_temp += (
                dt * self.K_SENSOR_LOSS * (self.inside_temp - self.inflow_temp)
            )

        d_t_cooler = (
            -p_electric_c + p_passive_loss_c + p_active_loss_c
        ) / self.C_COOLER
        self.cooler_temp += dt * d_t_cooler

        p_walls = self.K_WALLS * (outside_temp - self.inside_temp)
        p_vent = g_flow * self.C_AIR * (self.inflow_temp - self.inside_temp)
        d_t_in = (p_walls + p_vent + self.P_internal) / self.C_ROOM_EFF
        self.inside_temp += dt * d_t_in

        inside_temp_noisy = self.inside_temp + random.gauss(0, 0.1)
        inflow_temp_noisy = self.inflow_temp + random.gauss(0, 0.1)
        heater_temp_noisy = self.heater_temp + random.gauss(0, 0.1)
        cooler_temp_noisy = self.cooler_temp + random.gauss(0, 0.1)

        return (
            inside_temp_noisy,
            inflow_temp_noisy,
            heater_temp_noisy,
            cooler_temp_noisy,
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
