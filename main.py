import atexit
import threading
import time

from gpio_controller import GPIOController
from MedicineSchedule import handle_command, run_scheduler
from RequestTts import text_to_voice
from util import (
    auto_save_mic,
    auto_save_speaker,
    initialize_settings,
    wait_for_microphone,
    wait_for_network,
)
from WakeWord import wakeWord_forever

gpio = GPIOController(refresh_callback=lambda: None)
atexit.register(gpio.cleanup)

if __name__ == "__main__":
    
    if wait_for_microphone():
        time.sleep(2)
        auto_save_mic()
        auto_save_speaker()
    else:
        print("마이크를 찾을 수 없습니다.")
     
    wait_for_network()
    
    # initialize_settings()   
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # text_to_voice("안녕하세요. 저는 살가이라고 합니다. 살가이라고 불러주세요.")

    while True:
        gpio.set_mode("default")  # 기본 대기 상태 (파란 LED)

        try:
            recognized_text = wakeWord_forever()

            if recognized_text:
                try:
                    handle_command(recognized_text)
                except Exception as e:
                    print(f"명령 처리 중 오류 발생: {e}")
                    gpio.set_mode("error")  # 초록 LED
                    time.sleep(2)
                    gpio.set_mode("default")
        except Exception as e:
            print(f"웨이크워드 감지 오류: {e}")
            gpio.set_mode("error")
            time.sleep(2)
            gpio.set_mode("default")

        time.sleep(0.5)

            
