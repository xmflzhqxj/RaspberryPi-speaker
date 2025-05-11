import os
import subprocess

import requests

from config import BASE_URL, DUMMY_ID, LLM_VOICE_PATH, WAV_PATH
from gpio_controller import GPIOController

gpio = GPIOController(refresh_callback=lambda: None)

# 공통 LLM 응답 처리 함수
def send_audio_and_get_response(audio_path, url, params, expect_text=True, play_audio=True):
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
        print(f"오디오 파일이 존재하지 않거나 너무 작습니다: {audio_path}")
        gpio.set_mode("error")
        return "" if expect_text else False

    files = {"audio": open(audio_path, "rb")}
    try:
        response = requests.post(url, files=files, params=params)
        if response.status_code == 200:
            result = response.json()
            text = result.get("message", "")
            audio_url = result.get("file_url", "")

            print(text)
            
            if play_audio and audio_url:
                audio_data = requests.get(audio_url)
                if audio_data.status_code == 200:
                    with open(LLM_VOICE_PATH, "wb") as f:
                        f.write(audio_data.content)
                    subprocess.run(["mpg123", LLM_VOICE_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    print(f"음성 다운로드 실패: {audio_data.status_code}")
                    gpio.set_mode("error")
            return text if expect_text else True
        else:
            print(f"LLM 응답 실패: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"LLM 요청 예외: {e}")
        gpio.set_mode("error")
    finally:
        files["audio"].close()

    return "" if expect_text else False

# 일반 대화 또는 복약 체크
def conversation_and_check(responsetype="", schedule_id=None, user_id=None):
    url = f"{BASE_URL}/api/test2"
    real_schedule_id = schedule_id if responsetype == "check_medicine" else DUMMY_ID
    
    text = send_audio_and_get_response(WAV_PATH, url, {
        "userId": user_id,
        "scheduleId": real_schedule_id,
        "responsetype": responsetype
    }, expect_text=True)

    if responsetype == "check_medicine":
        taken_keywords = ["복용", "먹었", "약 먹", "다 먹", "드셨"]
        return any(keyword in text for keyword in taken_keywords)
    return text

# 복약 시간 알림 
def post_taking_medicine(schedule_id, user_id):
    url = f"{BASE_URL}/api/test2"
    dummy_path = "/home/pi/my_project/test.wav"
    return send_audio_and_get_response(dummy_path, url, {
        "userId": user_id,
        "scheduleId": schedule_id,
        "responsetype": "taking_medicine_time"
    }, expect_text=False)
