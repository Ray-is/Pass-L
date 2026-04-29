from time import sleep
from machine import Pin, PWM


class Safe:
    def __init__(self):
        self.safeOpen = False
        self.servo = PWM(Pin(0))
        self.servo.freq(50)

    def _set_servo_angle(self, angle):
        pulse_us = 500 + (angle / 180) * 1900
        self.servo.duty_u16(int((pulse_us / 20000) * 65535))

    def unlock_safe(self):
        if self.safeOpen:
            return
        for angle in range(0, 91, 1):
            self._set_servo_angle(angle)
            sleep(0.02)
        self.safeOpen = True
        print("Safe unlocked")

    def lock_safe(self):
        if not self.safeOpen:
            return
        for angle in range(90, -1, -1):
            self._set_servo_angle(angle)
            sleep(0.02)
        self.safeOpen = False
        print("Safe locked")


safe = Safe()

while True:
    safe.unlock_safe()
    sleep(3)
    safe.lock_safe()
    sleep(3)
