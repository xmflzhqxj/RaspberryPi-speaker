import audioop
import os
import subprocess
import time
import wave

import requests

from config import BASE_URL, WAV_PATH
from gpio_controller import GPIOController
from util import load_hw_device
from global_state import mic_lock
gpio = GPIOController(refresh_callback=lambda: None)

SILENCE_THRESHOLD = 1600  
SILENCE_DURATION = 1.5
CHUNK_SIZE = 1024
RATE = 44100
CHANNELS = 1

def record_audio():
    with mic_lock:
        try:
            print("음성 녹음중...")

            device = load_hw_device()       
            if not device.startswith("plughw:"):
                device = device.replace("hw:", "plughw:")

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
            start_time = time.time()
            max_recording_time = 20

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
                        break
                else:
                    silence_start = None

                if time.time() - start_time > max_recording_time:
                    print("녹음 최대 시간 초과로 종료")
                    break
                
            process.kill()        
            try:
                while process.stdout.read(CHUNK_SIZE):  # stdout 비우기
                    pass
            except Exception:
                pass
            process.wait()          

            if not frames:
                print("녹음된 데이터가 없습니다.")
                gpio.set_mode("error")
                return False
            
            with wave.open(WAV_PATH, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(RATE)
                wf.writeframes(b''.join(frames))

            return True

        except Exception as e:
            print(f"녹음 실패: {e}")
            gpio.set_mode("error")
            return False

def upload_stt():
    url = f"{BASE_URL}/api/stt"
    
    if not record_audio():
        print("녹음 실패")
        gpio.set_mode("error")
        return ""
    
    if not os.path.exists(WAV_PATH):
        gpio.set_mode("error")
        print("녹음 파일 없음")
        return ""

    if os.path.getsize(WAV_PATH) < 2048:
        print(f"녹음 파일이 너무 작습니다: {WAV_PATH}")
        gpio.set_mode("error")
        return ""

    try:
        with open(WAV_PATH, "rb") as f:
            response = requests.post(url, files={"audio": f})
            if response.status_code == 200:
                print(f"STT : {response.text.strip()}")
                return response.text.strip()
            else:
                print(f"STT 서버 응답 실패: {response.status_code}")
                gpio.set_mode("error")
                return ""
    except Exception as e:
        print(f"STT 서버 요청 실패: {e}")
        gpio.set_mode("error")
        return ""

if __name__ == "__main__":
    result = upload_stt()
    if result:
        print(f"인식 결과: {result}")
    else:
        print("인식된 결과가 없습니다.")
