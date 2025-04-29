import os
import subprocess

import requests

from config import BASE_URL, DUMMY_ID, LLM_VOICE_PATH, WAV_PATH


def conversation_and_check(responsetype="", schedule_id=None, user_id=None):
    url = f"{BASE_URL}/api/test2"

    if not os.path.exists(WAV_PATH) or os.path.getsize(WAV_PATH) < 1000:
        print(f"녹음 파일이 존재하지 않거나 너무 작습니다: {WAV_PATH}")
        return "" if responsetype != "check_medicine" else False

    if responsetype == "check_medicine":
        real_schedule_id = schedule_id
    else:
        real_schedule_id = DUMMY_ID

    files = {"audio": open(WAV_PATH, "rb")}
    params = {
        "userId": user_id,
        "scheduleId": real_schedule_id,
        "responsetype": responsetype
    }

    try:
        print(f"conversation_and_check 실행 시작 (responsetype: {responsetype})")
        response = requests.post(url, files=files, params=params)
        if response.status_code == 200:
            result = response.json()
            text = result.get("message", "")
            audio_url = result.get("file_url", "")

            print(f"LLM 텍스트 응답: {text}")

            if audio_url:
                audio_data = requests.get(audio_url)
                if audio_data.status_code == 200:
                    with open(LLM_VOICE_PATH, "wb") as f:
                        f.write(audio_data.content)

                    if os.path.exists(LLM_VOICE_PATH):
                        subprocess.run(["mpg123", LLM_VOICE_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        print("LLM 응답 음성 파일이 존재하지 않습니다.")
                else:
                    print(f"음성 다운로드 실패: {audio_data.status_code}")

            if responsetype == "check_medicine":
                taken_keywords = ["복용", "먹었", "약 먹", "다 먹", "드셨"]
                return any(keyword in text for keyword in taken_keywords)
            else:
                return text

        else:
            print(f"LLM 응답 실패: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"conversation_and_check 중 오류: {e}")
    finally:
        files["audio"].close()

    return False if responsetype == "check_medicine" else ""