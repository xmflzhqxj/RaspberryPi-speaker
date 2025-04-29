import audioop
import os
import subprocess
import time
import wave

import requests

from config import BASE_URL, WAV_PATH
from util import load_hw_device, suppress_alsa_errors

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
            "-f", "S16_LE",
            "-r", str(RATE),
            "-c", str(CHANNELS),
            "-t", "raw"
        ]

        frames = []
        silence_start = None

        with suppress_alsa_errors():
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE)

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
            process.wait()

        if not frames:
            print("녹음 데이터가 없습니다.")
            return False

        with wave.open(WAV_PATH, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))

        return True

    except Exception as e:
        print(f"녹음 실패: {e}")
        return False
    
def upload_stt():
    url = f"{BASE_URL}/api/stt"
    
    if record_audio():
        if os.path.exists(WAV_PATH):
            try:
                with open(WAV_PATH, "rb") as f:
                    response = requests.post(url, files={"audio": f})
                    if response.status_code == 200:
                        return response.text.strip()
                    else:
                        print(f"STT 서버 응답 실패: {response.status_code}")
                        return ""
            except Exception as e:
                print(f"STT 서버 요청 실패: {e}")
                return ""
        else:
            print("녹음 파일 없음")
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
