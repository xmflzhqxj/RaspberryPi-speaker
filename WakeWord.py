import time

import numpy as np
import pvporcupine
import pyaudio
from scipy.signal import resample

from RequestStt import upload_stt
from RequestTts import text_to_voice
from util import load_mic_index, suppress_alsa_errors

KEYWORD_PATH ="/home/pi/my_project/salgai_ko_raspberry-pi_v3_0_0.ppn"
MODEL_PATH = "/home/pi/my_project/porcupine_params_ko.pv"

def listen_for_wakeword():
    porcupine = None
    pa = None
    stream = None
    detected = False
    
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
                return

            pa = pyaudio.PyAudio()
            input_frame_length = int(porcupine.frame_length * 44100 / 16000)
            
            stream = pa.open(format=pyaudio.paInt16,
                     channels=1, rate=44100,input=True,
                     input_device_index=mic_index,
                     frames_per_buffer=input_frame_length)

        print("waiting wakeword 살가이...")

        while True:
            data = stream.read(input_frame_length, exception_on_overflow=False)
            pcm_44100 = np.frombuffer(data, dtype=np.int16)

            # 리샘플링해서 16000Hz 맞춤
            pcm_16000 = resample(pcm_44100, porcupine.frame_length)
            pcm_16000 = np.round(pcm_16000).astype(np.int16)
            
            if np.isnan(pcm_16000).any() or np.isinf(pcm_16000).any():
                print("NaN or Inf 포함된 프레임 – 스킵")
                continue
            
            result = porcupine.process(pcm_16000)
            
            if result >= 0:
                print("wakeword 살가이가 감지되었습니다.")
                detected = True
                break
            
    except Exception as e:
        print(f"초기화 에러:{e}")

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

        if detected:
            time.sleep(3)  # 장치 해제 시간 약간 주기
            text_to_voice("네?")
            return upload_stt()

def wakeWord_forever():
    while True:
        result_text = listen_for_wakeword()
        if result_text:
            return result_text
        print("\n'살가이' 감지 실패, 재시도 중...")
        time.sleep(1)

if __name__ == "__main__":
    wakeWord_forever()
