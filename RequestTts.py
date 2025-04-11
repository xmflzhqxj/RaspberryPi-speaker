import requests
from pydub import AudioSegment
from pydub.playback import play

from util import safe_play

# TTS API 서버 주소
TTS_API_URL = "http://3.34.179.85:8000/api/tts"

# TTS 수행 함수
def text_to_voice(text):
    try:
        payload = {"text": text}
        response = requests.post(TTS_API_URL, json=payload)

        if response.status_code == 200:
            with open("/home/pi/my_project/tts.mp3", "wb") as f:
                f.write(response.content)
            audio = AudioSegment.from_file("/home/pi/my_project/tts.mp3", format="mp3")
            safe_play(audio)
        else:
            print(f"상태코드: {response.status_code}, 메시지: {response.text}")

    except Exception as e:
        print(f"예외 {e}")

# 테스트 실행
if __name__ == "__main__":
    print("TTS 테스트 시작") 
    text_to_voice("지금은 복약시간 입니다 약을 복용해주세요.")
