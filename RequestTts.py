import requests
from pydub import AudioSegment

from config import BASE_URL
from gpio_controller import GPIOController
from util import safe_play

gpio = GPIOController(refresh_callback=lambda: None, skip_callback=lambda: None) # 시각적 LED 표시

# api에서 진행되는 TTS 코드
# from gtts import gTTS 구글 gTTS 라이브러리
# from playsound import playsound

# def text_to_voice(text): // .mp3 파일 실행
#     tts = gTTS(text=text, lang='ko')
#     fileName = "/home/pi/my_project/tts.mp3"
#     tts.save(fileName)
#     playsound(fileName)
#     print("TTS complete")

# TTS 수행 함수
def text_to_voice(text):
    url = f"{BASE_URL}/api/tts" # api에 요청
    gpio.set_mode("llmtts")
    try:
        payload = {"text": text}
        response = requests.post(url, json=payload)

        if response.status_code == 200:
            with open("/home/pi/my_project/tts.mp3", "wb") as f:
                f.write(response.content)
            audio = AudioSegment.from_file("/home/pi/my_project/tts.mp3", format="mp3")
            safe_play(audio)
        else:
            print(f"상태코드: {response.status_code}, 메시지: {response.text}")

    except Exception as e:
        gpio.set_mode("error")
        print(f"예외 {e}")

    gpio.set_mode("default")
# 테스트 실행
if __name__ == "__main__":
    print("TTS 테스트 시작") 
    text_to_voice("지금은 복약시간 입니다 약을 복용해주세요.")
