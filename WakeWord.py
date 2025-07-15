import time

import numpy as np 
import pvporcupine # wakeword 감지를 위한 라이브러리
import pyaudio
import requests
from scipy.signal import resample

import global_state
from config import BASE_URL, DOSAGE_TIME, FE_USER_ID
from global_state import mic_lock
from gpio_controller import GPIOController
from llmTts import post_intent
from RequestStt import upload_stt
from RequestTts import text_to_voice
from util import load_mic_index, suppress_alsa_errors

gpio = GPIOController(refresh_callback=lambda: None, skip_callback=lambda: None)

KEYWORD_PATH = "웨이크워드 파일명"
MODEL_PATH = "언어모델 파일명"
MAX_CONFIRMATION_WAIT = DOSAGE_TIME

# wakeword 감지를 알려주는 함수
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
        print(f"POST 요청 중 오류 발생: {e}")
        gpio.set_mode("error")
        return False

# wakeword를 감지하는 함수
def listen_for_wakeword():
    porcupine = None
    pa = None
    stream = None
    global wakeword_detection
    
    try:
        with suppress_alsa_errors():
            porcupine = pvporcupine.create(
                access_key="개인키",
                keyword_paths=[KEYWORD_PATH],
                model_path=MODEL_PATH
            )

            mic_index = load_mic_index()
            if mic_index is None:
                print("저장된 마이크 인덱스를 찾을 수 없습니다.")
                gpio.set_mode("error")
                return None

            pa = pyaudio.PyAudio()
            input_frame_length = int(porcupine.frame_length * 44100 / 16000) # 웨이크워드의 frequency에 맞게 변환

            print("waiting wakeword...") 

            while True:
                # 마이크 중복 방지
                if not mic_lock.acquire(timeout=0.1):
                    time.sleep(0.2)
                    continue

                try:
                    stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=44100,
                        input=True,
                        input_device_index=mic_index,
                        frames_per_buffer=input_frame_length
                    )

                    data = stream.read(input_frame_length, exception_on_overflow=False)
                    pcm_44100 = np.frombuffer(data, dtype=np.int16)
                    pcm_16000 = resample(pcm_44100, porcupine.frame_length)
                    pcm_16000 = np.round(pcm_16000).astype(np.int16)

                    if np.isnan(pcm_16000).any() or np.isinf(pcm_16000).any():
                        continue

                    result = porcupine.process(pcm_16000)
    
                    if result >= 0:
                        print("wakeword 살가이가 감지되었습니다.")
                        global_state.wakeword_detection = True
                        post_wakeword()
                        gpio.set_mode("wakeword")

                        # 자원 충돌 방지
                        if stream:
                            stream.stop_stream()
                            stream.close()
                            stream = None
                        if pa:
                            pa.terminate()
                            pa = None
                        if porcupine:
                            porcupine.delete()
                            porcupine = None
                        mic_lock.release()
                        time.sleep(1.5)

                        text_to_voice("네?")
                        user_text = upload_stt() # 사용자 음성 녹음

                        if user_text:
                            post_intent(FE_USER_ID) # 의도 파악 함수 실행
                            
                        gpio.set_mode("default") 
                        return user_text

                except Exception as e:
                    print(f"wakeword 오류: {e}")
                    gpio.set_mode("error")
                    time.sleep(2)
                    gpio.set_mode("default")  

                finally:
                    try:
                        if stream:
                            if stream.is_active():
                                stream.stop_stream()
                            stream.close()
                            stream = None
                        mic_lock.release()
                    except:
                        pass

    except Exception as e:
        print(f"초기화 에러: {e}")
        gpio.set_mode("error")
        time.sleep(2)
        gpio.set_mode("default")

    # 마이크 자원 반드시 해제
    finally:
        if stream:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
            except:
                pass
        if pa:
            try:
                pa.terminate()
            except:
                pass
        if porcupine:
            try:
                porcupine.delete()
            except:
                pass
    

# 웨이크 워드 인식 함수 무한 루프
def wakeWord_forever():
    while True:
        gpio.set_mode("default")  
        result_text = listen_for_wakeword()
        
        global_state.wakeword_detection = False
        
        if result_text:
            return result_text
        print("\n'살가이' 감지 실패, 재시도 중...")
        gpio.set_mode("error")
        time.sleep(1)
        gpio.set_mode("default")  


if __name__ == "__main__":
    wakeWord_forever()
