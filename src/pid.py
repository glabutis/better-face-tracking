import time


class PID:
    """Simple PID controller for a single axis."""

    def __init__(self, kp: float = 0.4, ki: float = 0.0, kd: float = 0.05):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time: float | None = None

    def compute(self, error: float) -> float:
        now = time.monotonic()
        if self._prev_time is None:
            dt = 0.033  # assume ~30 fps on first call
        else:
            dt = max(0.001, now - self._prev_time)

        self._integral += error * dt
        self._integral = max(-1.0, min(1.0, self._integral))  # anti-windup clamp

        derivative = (error - self._prev_error) / dt

        output = self.kp * error + self.ki * self._integral + self.kd * derivative

        self._prev_error = error
        self._prev_time = now
        return output

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None

    def update_gains(self, kp: float, ki: float, kd: float):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.reset()
