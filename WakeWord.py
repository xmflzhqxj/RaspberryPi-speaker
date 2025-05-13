import time

import numpy as np
import pvporcupine
import pyaudio
import requests
from scipy.signal import resample
from datetime import datetime

from config import BASE_URL,DOSAGE_TIME,USER_ID
from global_state import pending_alerts
from gpio_controller import GPIOController
from llmTts import post_intent,conversation_and_check
from MedicineSchedule import handle_medicine_confirmation
from RequestStt import upload_stt
from RequestTts import text_to_voice
from util import load_mic_index, suppress_alsa_errors

gpio = GPIOController(refresh_callback=lambda: None)

KEYWORD_PATH ="/home/pi/my_project/salgai_ko_raspberry-pi_v3_0_0.ppn"
MODEL_PATH = "/home/pi/my_project/porcupine_params_ko.pv"
MAX_CONFIRMATION_WAIT = DOSAGE_TIME 
FE_USER_ID = 2

def post_wake(user_id) :
    url = f"{BASE_URL}/api/wake"
    params = {"user_id": user_id}

    try:
        response = requests.post(url, params=params)

        if response.status_code == 200:
            return response.text
        else:
            print(f"서버 응답 실패: {response.status_code} - {response.text}")
            gpio.set_mode("error")
            return None
    except Exception as e:
        print(f"요청 중 오류 발생: {e}")
        gpio.set_mode("error")
        return None    
    
def post_wakeword():
    url = f"{BASE_URL}/api/wake"
    params = {"user_id": FE_USER_ID}

    try:
        response = requests.post(url, params=params)
        
        if response.status_code == 200:
            print("서버에 wake 메시지 전송 완료")
            return True
        else:
            print(f"서버 응답 실패: {response.status_code} - {response.text}")
            gpio.set_mode("error")
            return False
    except Exception as e:
        print(f" POST 요청 중 오류 발생: {e}")
        gpio.set_mode("error")
        return False
    
def listen_for_wakeword():
    porcupine = None
    pa = None
    stream = None
    detected = False
    
    gpio.set_mode("default")
    
    try:
        with suppress_alsa_errors():
            porcupine = pvporcupine.create(
                access_key="ni04jcIMpIiFP81v3fdVRyfmtPwUM6t6fKm7/1UXnW8IdpQ+AsZcbw==",
                keyword_paths=[KEYWORD_PATH],
                model_path=MODEL_PATH
            )

            mic_index = load_mic_index()
            if mic_index is None:
                print("저장된 마이크 인덱스를 찾을 수 없습니다.")
                gpio.set_mode("error")
                return

            pa = pyaudio.PyAudio()
            input_frame_length = int(porcupine.frame_length * 44100 / 16000)

            stream = pa.open(format=pyaudio.paInt16,
                             channels=1, rate=44100, input=True,
                             input_device_index=mic_index,
                             frames_per_buffer=input_frame_length)

        print("waiting wakeword 살가이...")

        while True:
            data = stream.read(input_frame_length, exception_on_overflow=False)
            pcm_44100 = np.frombuffer(data, dtype=np.int16)

            pcm_16000 = resample(pcm_44100, porcupine.frame_length)
            pcm_16000 = np.round(pcm_16000).astype(np.int16)

            if np.isnan(pcm_16000).any() or np.isinf(pcm_16000).any():
                continue

            result = porcupine.process(pcm_16000)

            if result >= 0:
                print("wakeword 살가이가 감지되었습니다.")
                post_wakeword()
                
                gpio.set_mode("wakeword")
                detected = True
                break

    except Exception as e:
        print(f"초기화 에러:{e}")
        gpio.set_mode("error")

    finally:
        try:
            if stream and stream.is_active():
                stream.stop_stream()
            if stream:
                stream.close()
            if pa:
                pa.terminate()
            if porcupine:
                porcupine.delete()  

        except Exception as e:
            print(f"stream 정리 중 오류: {e}")
            gpio.set_mode("error")

        if detected:
            time.sleep(1.5)
            text_to_voice("네?")

            user_text = upload_stt()

            if user_text:
                has_confirmation_alert = False
                for alert in list(pending_alerts):
                    if alert.get("wait_for_confirmation"):
                        elapsed = (datetime.now() - alert["confirmation_started_at"]).total_seconds() / 60
                        if elapsed <= MAX_CONFIRMATION_WAIT:
                            has_confirmation_alert = True
                            is_taken = conversation_and_check(
                                responsetype="check_medicine",
                                schedule_id=alert["schedule_id"],
                                user_id=USER_ID
                            )
                            if is_taken:
                                handle_medicine_confirmation(alert)
                            
                                return user_text

                if not has_confirmation_alert:
                    response = post_intent(user_id=FE_USER_ID)

            else:
                text_to_voice("녹음에 실패했습니다.")
                gpio.set_mode("error")
                return None



def wakeWord_forever():
    while True:
        result_text = listen_for_wakeword()
        if result_text:
            return result_text
        print("\n'살가이' 감지 실패, 재시도 중...")
        gpio.set_mode("error")
        time.sleep(1)

if __name__ == "__main__":
    wakeWord_forever()
