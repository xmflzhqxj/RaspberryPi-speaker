import threading
import time

from commandHandler import handle_command
from MedicineSchedule import run_scheduler
from RequestTts import text_to_voice
from util import auto_save_mic, auto_save_speaker, wait_for_microphone, wait_for_network
from WakeWord import wakeWord_forever

if __name__ == "__main__":
    
    if wait_for_microphone(): # 마이크 연결 기다리기
        time.sleep(2)
        auto_save_mic()
        auto_save_speaker()
        
    else :
        print("마이크를 찾을 수 없습니다.")
        
    wait_for_network() # 네트워크 연결 기다리기
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    text_to_voice("안녕하세요. 저는 살가이라고 합니다. 살가이라고 불러주세요.")
    #살가이를 감지하면 STT->TTS 반복
    while True:
        recognized_text = wakeWord_forever()
        
        if recognized_text:
            handle_command(recognized_text)
 
