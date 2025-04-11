import contextlib
import json
import os
import subprocess
import sys
import time

import pyaudio
import requests

CONFIG_PATH = "/home/pi/my_project/.mic_config"
SPEAKER_CONFIG_PATH = "/home/pi/my_project/.speaker_config"

@contextlib.contextmanager
def suppress_alsa_errors():
    try:
        # flush any pending stderr
        sys.stderr.flush()
        devnull = os.open(os.devnull, os.O_WRONLY)
        original_stderr_fd = os.dup(2)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(original_stderr_fd, 2)
        os.close(original_stderr_fd)
        os.close(devnull)

@contextlib.contextmanager
def safe_play(audio_segment):
    speaker_device = load_speaker_device()

    # 스피커가 mono 지원 안 할 수도 있으므로 stereo로 변경
    if audio_segment.channels == 1:
        audio_segment = audio_segment.set_channels(2)

    audio_segment = audio_segment.set_frame_rate(44100)

    temp_path = "/tmp/temp_audio.wav"
    audio_segment.export(temp_path, format="wav")

    try:
        result = subprocess.run(["aplay", "-D", speaker_device, temp_path], capture_output=True, text=True)
    except Exception as e:
        print(f"에러 {e}")

#llm 전 복용함을 알리는 command
TAKEN_PATTERNS = [
    r"먹(었|었어요|었습니다|었어)",
    r"복용(했|했어요|했습니다)",
    r"\b(응|네)\b",
]

def auto_save_speaker():
    try:
        result = subprocess.run(['aplay', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = result.stdout.splitlines()
        target_keywords = ['usb', 'audio', 'speaker']
        speaker_hw = None

        for line in lines:
            line = line.strip().lower()
            if line.startswith('card ') and any(k in line for k in target_keywords):
                parts = line.split(':')
                card_info = parts[0].strip()         # 'card 2'
                card_num = card_info.split()[1]
                device_info = parts[1].split(',')[1].strip()  # 'device 0'
                device_num = device_info.split()[1]
                speaker_hw = f"hw:{card_num},{device_num}"
                break

        if not speaker_hw:
            print("USB 스피커 자동 감지 실패, 기본값 사용 hw:0,0")
            speaker_hw = "hw:0,0"

        with open(SPEAKER_CONFIG_PATH, "w") as f:
            json.dump({"speaker_device": speaker_hw}, f)

        print(f"스피커 설정 저장 완료: {speaker_hw}")

    except Exception as e:
        print(f"스피커 감지 실패: {e}")
        
def load_speaker_device():
    if os.path.exists(SPEAKER_CONFIG_PATH):
        with open(SPEAKER_CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("speaker_device", "hw:0,0")
    return "hw:0,0"

def save_mic_index(index):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    try:
        pa = pyaudio.PyAudio()
        dev = pa.get_device_info_by_index(index)
        target_name = dev['name'].strip().lower()  # 소문자 통일
        pa.terminate()
    except Exception as e:
        print(f"마이크 이름 확인 실패: {e}")
        return

    try:
        result = subprocess.run(['arecord', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = result.stdout.splitlines()
        hw_device = None

        for line in lines:
            line = line.strip()
            if line.startswith('card '):
                parts = line.split(':')
                card_info = parts[0].strip()         # 'card 0'
                card_num = card_info.split()[1]     
                device_info = parts[1].split(',')[1].strip()  # 'device 0: USB Audio [USB Audio]'
                device_num = device_info.split()[1]  
                name_info = parts[1].split(',')[0].strip()    # 'Device [USB Audio Device]'
                name_clean = name_info.split('[')[-1].replace(']', '').strip().lower()

                if name_clean in target_name or target_name in name_clean:
                    hw_device = f"hw:{card_num},{device_num}"
                    break

        if not hw_device:
            print("마이크 이름 일치 실패, fallback 시도")
            hw_device = "hw:0,0"  # fallback 더 안전하게 수정

        with open(CONFIG_PATH, "w") as f:
            json.dump({
                "mic_index": index,
                "hw_device": hw_device
            }, f)

        print(f"마이크 설정 저장 완료: index={index}, device={hw_device}")

    except Exception as e:
        print(f"arecord 장치 추출 실패: {e}")


def auto_save_mic():
    pa = pyaudio.PyAudio()
    selected_index = None
# 가짜 장치 제외할 키워드

    for i in range(pa.get_device_count()):
        try:
            dev = pa.get_device_info_by_index(i)
            name = dev['name'].lower()

            if (
                dev.get('maxInputChannels', 0) > 0 and
                any(k in name for k in ['usb', 'mic', 'audio'])  # 진짜 마이크 키워드
            ):
                selected_index = i
                break
        except Exception:
            continue

    # 못 찾으면 첫 번째 '입력 장치'를 기준으로 하지만, 여기도 예외 필터 추가
    if selected_index is None:
        for i in range(pa.get_device_count()):
            try:
                dev = pa.get_device_info_by_index(i)
                if dev.get('maxInputChannels', 0) > 0:
                    selected_index = i
                    break
            except Exception:
                continue

    pa.terminate()

    if selected_index is not None:
        print(f"자동으로 마이크 선택됨: index={selected_index}")
        save_mic_index(selected_index)
    else:
        print("사용 가능한 마이크를 찾을 수 없습니다.")

def load_hw_device():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("hw_device", "hw:0,0")  # 없으면 기본값 반환
    return "hw:0,0"

def load_mic_index():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("mic_index")
    return None

def wait_for_network(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get("http://3.34.179.85:8000", timeout=3)
            return True
        except:
            time.sleep(2)
    print("네트워크 연결 실패")
    return False

def wait_for_microphone(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            pa = pyaudio.PyAudio()
            count = pa.get_device_count()
            for i in range(count):
                dev = pa.get_device_info_by_index(i)
                if dev.get('maxInputChannels', 0) > 0:
                    pa.terminate()
                    return True
            pa.terminate()
        except Exception as e:
            print(f"마이크 확인 실패: {e}")
        time.sleep(2)
    print("마이크 준비 실패")
    return False
