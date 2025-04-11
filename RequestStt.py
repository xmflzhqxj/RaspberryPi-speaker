import audioop
import os
import subprocess
import time
import wave

import requests

from util import load_hw_device

FILE_PATH = "/home/pi/my_project/stt.wav"
API_URL = "http://3.34.179.85:8000/api/stt"

SILENCE_THRESHOLD = 100 # 말을 안할 때 진폭
SILENCE_DURATION = 3  # 말 멈추고 3초 뒤 종료
CHUNK_SIZE = 1024
RATE = 44100
CHANNELS = 1

def record_audio():
    try:
        print("음성 녹음중...")

        device = load_hw_device()
        cmd = [
            "arecord",
            "-D", device,
            "-f", "cd",
            "-r", str(RATE),
            "-c", str(CHANNELS),
            "-t", "raw"
        ]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        frames = []
        silence_start = None

        while True:
            data = process.stdout.read(CHUNK_SIZE)
            if not data:
                break

            frames.append(data)
            rms = audioop.rms(data, 2)

            if rms < SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > SILENCE_DURATION:
                    print("말이 멈췄다고 판단됨. 녹음 종료.")
                    break
            else:
                silence_start = None

        process.terminate()

        # wav 파일 저장
        with wave.open(FILE_PATH, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        print("녹음 파일 저장 완료:", FILE_PATH)
        return True

    except Exception as e:
        print(f"녹음 실패: {e}")
        return False
    
def upload_stt():
    if record_audio():
        if os.path.exists(FILE_PATH):
            try:
                with open(FILE_PATH, "rb") as f:
                    response = requests.post(API_URL, files={"audio": f})
                    return response.text.strip()
            except Exception as e:
                print(f"API 요청 실패: {e}")
                return ""
        else:
            print("저장된 녹음 파일이 없습니다.")
            return ""
    else:
        print("녹음 실패")
        return ""
    
if __name__ == "__main__":
    result = upload_stt()
    if result:
        print(f"인식 결과: {result}")
    else:
        print("인식된 결과가 없습니다.")
