import os
import subprocess
import time
 
import requests

import global_state
from config import BASE_URL, DUMMY_ID, DUMMY_PATH, LLM_VOICE_PATH, WAV_PATH
from global_state import mic_lock
from gpio_controller import GPIOController
from util import load_speaker_device

gpio = GPIOController(refresh_callback=lambda: None, skip_callback=lambda: None)

# 웨이크워드 감지 시 현재 처리 중인 작업을 중단하는 함수
def wakeword_interrupt(result, expect_text,params=None): # 
    if params and params.get("responsetype") == "intent": 
        return None
    
    # 전역 웨이크워드 감지 플래그가 True인 경우 (웨이크워드가 감지됨)
    if global_state.wakeword_detection:
        print("웨이크워드 감지로 중단")
        return result if expect_text else bool(result)
    return None
    
# 공통 LLM 응답 처리 함수
def send_audio_and_get_response(audio_path, url, params, expect_text=True, play_audio=True):
    result = {}

    #  함수 시작 시 웨이크워드 중단 여부 확인
    interrupted = wakeword_interrupt(result, expect_text,params)
    if interrupted is not None:
        return interrupted

    # 오디오 파일 유효성 검사
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000: 
        print(f"오디오 파일이 존재하지 않거나 너무 작습니다: {audio_path}")
        gpio.set_mode("error")
        time.sleep(2)
        gpio.set_mode("default")
        return {} if expect_text else False
    
    files = {"audio": open(audio_path, "rb")}
    try:
        # LLM API에 오디오 파일 전송 (POST 요청)
        response = requests.post(url, files=files, params=params)

        # 응답 수신 중 웨이크워드 중단 여부 다시 확인
        interrupted = wakeword_interrupt(result, expect_text,params)
        if interrupted is not None:
            return interrupted 

        #  LLM 응답 처리
        if response.status_code == 200:
            result = response.json()
            text = result.get("message", "")
            with open("requirements.txt", "w") as f:
                f.write(text.strip() + "\n")

            audio_url = result.get("file_url", "")

            # 음성 응답 재생 (play_audio가 True이고 audio_url이 있을 경우)
            if play_audio and audio_url:
                audio_data = requests.get(audio_url) 

                # 음성 다운로드 중 웨이크워드 중단 여부 다시 확인
                interrupted = wakeword_interrupt(result, expect_text,params)
                if interrupted is not None:
                    return interrupted
                
                if audio_data.status_code == 200:
                    with open(LLM_VOICE_PATH, "wb") as f:
                        f.write(audio_data.content)

                    wait_count = 0
                    
                    # 마이크가 잠겨있는 동안 대기 (마이크 사용 중인 경우 재생 방지)
                    while mic_lock.locked() and wait_count < 10:
                        time.sleep(0.5)
                        wait_count += 1

                    print(f"LLM : {text}")
                    gpio.set_mode("llmtts")

                    #  음성 재생 직전 웨이크워드 중단 여부 마지막 확인
                    interrupted = wakeword_interrupt(result, expect_text,params)
                    if interrupted is not None:
                        return interrupted
                    
                    speaker_device = load_speaker_device() # 스피커 설정 
                    proc = subprocess.run(
                        ["mpg123", "-o", "alsa", "-a", speaker_device, LLM_VOICE_PATH],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    if proc.returncode != 0:
                        print(f"재생 실패: return code {proc.returncode}")
                        print(f"stderr: {proc.stderr.decode()}")
                        gpio.set_mode("error")
                        time.sleep(2)
                    else:
                        gpio.set_mode("default")  
                else:
                    print(f"음성 다운로드 실패: {audio_data.status_code}")
                    gpio.set_mode("error")
                    time.sleep(2)
            else:
                gpio.set_mode("default")  
        else:
            print(f"LLM 응답 실패: {response.status_code} - {response.text}")
            gpio.set_mode("error")
            time.sleep(2)

    except Exception as e:
        print(f"LLM 요청 예외: {e}")
        gpio.set_mode("error")
        time.sleep(2)
    finally:
        files["audio"].close()

    return result if expect_text else bool(result)

# 일반 대화 또는 복약 체크
def conversation_and_check(responsetype="", schedule_id=None, user_id=None):
    gpio.set_mode("thinking")
    url = f"{BASE_URL}/api/FEtest"
    real_schedule_id = schedule_id if responsetype == "check_medicine" else DUMMY_ID

    result = send_audio_and_get_response(WAV_PATH, url, {
        "userId": user_id,
        "scheduleId": real_schedule_id,
        "responsetype": responsetype
    }, expect_text=True)

    if responsetype == "check_medicine":
        return result.get("success", None) # 복용 성공 여부 받아오기

    return result.get("message", "")


# 복약 시간 알림 
def post_taking_medicine(schedule_id, user_id):
    gpio.set_mode("thinking")
    url = f"{BASE_URL}/api/FEtest"
    return send_audio_and_get_response(DUMMY_PATH, url, {
        "userId": user_id,
        "scheduleId": schedule_id,
        "responsetype": "taking_medicine_time"
    }, expect_text=False)

# 사용자의 음성 명령 의도를 판단하는 함수
def post_intent(user_id):
    gpio.set_mode("thinking")
    url = f"{BASE_URL}/api/FEtest"
    return send_audio_and_get_response(WAV_PATH, url, {
        "userId": user_id,
        "scheduleId": DUMMY_ID,
        "responsetype": "intent"
    }, expect_text=True)
    
