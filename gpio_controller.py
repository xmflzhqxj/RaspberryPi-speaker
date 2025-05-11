import threading
import time
from datetime import datetime

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False
    class GPIO:
        BCM = OUT = IN = HIGH = LOW = PUD_UP = None
        @staticmethod
        def setmode(*args, **kwargs): pass
        @staticmethod
        def setup(*args, **kwargs): pass
        @staticmethod
        def output(*args, **kwargs): pass
        @staticmethod
        def input(*args): return 1
        @staticmethod
        def cleanup(): pass

# 핀 번호 설정
RED_LED = 17
BLUE_LED = 27
GREEN_LED = 22
SWITCH = 23

class GPIOController:
    def __init__(self, refresh_callback):
        self.refresh_callback = refresh_callback
        self.initialized = False
        self.initialized = self._setup_gpio() 
        if self.initialized:
            self._start_switch_monitor()

    def _setup_gpio(self):
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(RED_LED, GPIO.OUT)
            GPIO.setup(BLUE_LED, GPIO.OUT)
            GPIO.setup(GREEN_LED, GPIO.OUT)
            GPIO.setup(SWITCH, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self.set_mode("default")
            return True
        except Exception as e:
            print(f"GPIO 설정 중 오류 발생: {e}")
            return False

    def _start_switch_monitor(self):
        def monitor():
            while True:
                try:
                    if GPIO.input(SWITCH) == GPIO.LOW:
                        self.refresh_callback()
                        time.sleep(1)
                except Exception as e:
                    print(f"스위치 모니터링 오류: {e}")
                time.sleep(0.1)

        threading.Thread(target=monitor, daemon=True).start()

    def set_mode(self, mode):
        if not self.initialized:
            return
        GPIO.output(RED_LED, GPIO.LOW)
        GPIO.output(BLUE_LED, GPIO.LOW)
        GPIO.output(GREEN_LED, GPIO.LOW)
        if mode == "default":
            GPIO.output(BLUE_LED, GPIO.HIGH)
        elif mode == "wakeword":
            GPIO.output(RED_LED, GPIO.HIGH)
        elif mode == "error":
            GPIO.output(GREEN_LED, GPIO.HIGH)

    def cleanup(self):
        if self.initialized:
            GPIO.cleanup()
