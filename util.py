import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time

import pyaudio
import requests

MIC_CONFIG_PATH = "/home/pi/my_project/.mic_config"
SPEAKER_CONFIG_PATH = "/home/pi/my_project/.speaker_config"


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

@contextlib.contextmanager
def suppress_alsa_errors():
    try:
        sys.stderr.flush()
        devnull = os.open(os.devnull, os.O_WRONLY)
        original_stderr_fd = os.dup(2)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(original_stderr_fd, 2)
        os.close(original_stderr_fd)
        os.close(devnull)

def auto_save_mic():
    pa = pyaudio.PyAudio()
    selected_index = None

    for i in range(pa.get_device_count()):
        try:
            dev = pa.get_device_info_byindex(i)
            name = dev['name'].lower()

            if dev.get('maxInputChannels', 0) > 0 and any(k in name for k in ['usb', 'mic', 'audio']):
                selected_index = i
                break
        except Exception:
            continue

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
        save_mic_index(selected_index)
    else:
        print("사용 가능한 마이크를 찾지 못했습니다.")

def save_mic_index(index):
    os.makedirs(os.path.dirname(MIC_CONFIG_PATH), exist_ok=True)
    pa = pyaudio.PyAudio()
    dev = pa.get_device_info_by_index(index)
    target_name = dev['name'].strip().lower()
    pa.terminate()

    result = subprocess.run(['arecord', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = result.stdout.splitlines()
    hw_device = None

    for line in lines:
        if line.lower().startswith('card '):
            parts = line.split(':')
            card_info = parts[0].strip()
            card_num = card_info.split()[1]
            device_info = parts[1].split(',')[1].strip()
            device_num = device_info.split()[1]
            name_info = parts[1].split(',')[0].strip()
            name_clean = name_info.split('[')[-1].replace(']', '').strip().lower()

            if name_clean in target_name or target_name in name_clean:
                hw_device = f"hw:{card_num},{device_num}"
                break

    if not hw_device:
        print("마이크 hw:0,0으로 설정합니다.")
        hw_device = "hw:0,0"

    with open(MIC_CONFIG_PATH, "w") as f:
        json.dump({"mic_index": index, "hw_device": hw_device}, f)
    print(f"마이크 설정 저장 완료: index={index}, device={hw_device}")

def auto_save_speaker():
    result = subprocess.run(['aplay', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = result.stdout.splitlines()
    speaker_hw = None

    for line in lines:
        if line.lower().startswith('card ') and any(k in line.lower() for k in ['usb', 'speaker']) and 'hdmi' not in line.lower():
            parts = line.split(':')
            card_info = parts[0].strip()
            card_num = card_info.split()[1]
            device_info = parts[1].split(',')[1].strip()
            device_num = device_info.split()[1]
            speaker_hw = f"hw:{card_num},{device_num}"
            break

    if not speaker_hw:
        print("스피커 hw:0,0으로 설정합니다.")
        speaker_hw = "hw:0,0"

    with open(SPEAKER_CONFIG_PATH, "w") as f:
        json.dump({"speaker_device": speaker_hw}, f)
    print(f"스피커 설정 저장 완료: device={speaker_hw}")

def load_hw_device():
    if os.path.exists(MIC_CONFIG_PATH):
        with open(MIC_CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("hw_device", "hw:0,0")
    return "hw:0,0"

def load_speaker_device():
    if os.path.exists(SPEAKER_CONFIG_PATH):
        with open(SPEAKER_CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("speaker_device", "hw:0,0")
    return "hw:0,0"

import threading


#코드 실행 중 스피커/마이크 바꿀 경우
def device_monitor_thread(interval=5):
    last_mic = None
    last_speaker = None

    while True:
        try:
            # 현재 연결된 마이크/스피커 상태 읽기
            result_mic = subprocess.run(['arecord', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            result_speaker = subprocess.run(['aplay', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            mic_devices = result_mic.stdout.strip()
            speaker_devices = result_speaker.stdout.strip()

            if mic_devices != last_mic:
                print("마이크 장치 목록 변경됨. 재설정합니다.")
                auto_save_mic()
                last_mic = mic_devices

            if speaker_devices != last_speaker:
                print("스피커 장치 목록 변경됨. 재설정합니다.")
                auto_save_speaker()
                last_speaker = speaker_devices

        except Exception as e:
            print(f"장치 감시 중 오류 발생: {e}")

        time.sleep(interval)

def load_mic_index():
    if os.path.exists(MIC_CONFIG_PATH):
        with open(MIC_CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("mic_index", None)
    return None


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
                    print("마이크 감지 완료")
                    return True
            pa.terminate()
        except Exception as e:
            print(f"마이크 확인 실패: {e}")
        time.sleep(2)
    print("마이크 연결 실패")
    return False

def wait_for_network(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get("http://3.34.179.85:8000", timeout=5)
            return True
        except Exception as e:
            print(f"재시도중... 에러: {e}")
            time.sleep(2)
    print("서버 연결 실패")
    return False


def device_monitor_thread(interval=10):
    from util import auto_save_mic, auto_save_speaker

    def monitor():
        while True:
            print("마이크/스피커 다시 감지 중...")
            auto_save_mic()
            auto_save_speaker()
            time.sleep(interval)

    t = threading.Thread(target=monitor, daemon=True)
    t.start()

korean_number_map = {
    "영": 0, "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "백": 100, "천": 1000
}

def parse_korean_number(text):
    text = text.replace(" ", "").replace('"', '').replace('번', '').replace('입니다', '')
    
    if text in korean_number_map:
        return korean_number_map[text], text  # 숫자와 원래 한글 동시 반환
    elif "십" in text:
        parts = text.split("십")
        left = korean_number_map.get(parts[0], 1)
        right = korean_number_map.get(parts[1], 0) if len(parts) > 1 else 0
        return left * 10 + right, text
    else:
        return None, None
    
def listen_number(word, default_value=0, time_count = ""):
    from RequestStt import upload_stt
    from RequestTts import text_to_voice

    retry_count = 0
    text_to_voice(f"{word}를 말씀해주세요.")
    while retry_count < 3:
        stt_result = upload_stt()

        if stt_result:
            stt_result = stt_result.strip()

            # "기본값"이라고 말하면 바로 기본값 사용
            if "기본" in stt_result: 
                text_to_voice("사용자가 기본값을 요청했습니다.")
                return default_value

            # 숫자 추출
            numbers = re.findall(r'\d+', stt_result)

            if numbers:
                value =  int(numbers[0])
                unit = '분' if time_count == 'time' else '번' if time_count == 'count' else ''
                text_to_voice(f"{word} {value}{unit} 입니다.")
                return value
            
            else:
                value = parse_korean_number(stt_result)
                if value[0] is not None:
                    num_value, original_text = value
                    unit = '분' if time_count == 'time' else '번' if time_count == 'count' else ''
                    text_to_voice(f"{word} {original_text}{unit} 입니다.")
                    return num_value
        
        
        # 실패한 경우
        retry_count += 1
        text_to_voice("다시 말씀해주세요.")

    # 3회 모두 실패 → 기본값
    text_to_voice(f"3회 실패. {word} {default_value}입니다.")
    return default_value

CONFIG_PATH = "/home/pi/my_project/config.py" 

def save_config(user_id, dosage_time, dosage_count, meal_time, induce_time):
    content = f"""# 서버 기본 주소
BASE_URL = "http://3.34.179.85:8000"

# 사용자 ID
USER_ID = {user_id}

WAV_PATH = "/home/pi/my_project/stt.wav"
LLM_VOICE_PATH = "/home/pi/my_project/llm_answer.mp3"

# 복약 리마인더 설정
DOSAGE_TIME = {dosage_time}
DOSAGE_COUNT = {dosage_count}
MEAL_TIME = {meal_time}
INDUCE_TIME = {induce_time}
DUMMY_ID = -1
"""
    with open(CONFIG_PATH, "w") as f:
        f.write(content)

def initialize_settings():
    print("▶ 초기 설정을 음성으로 입력해주세요:")

    user_id = listen_number(word = "사용자 ID", default_value=1,time_count = "count")
    dosage_time = listen_number(word = "복약 실패 후 재알림 간격", default_value=5, time_count = "time")
    dosage_count = listen_number(word = "복약 실패 최대 재시도 횟수", default_value=3, time_count = "count")
    meal_time = listen_number(word = "복약 전 식사 체크 시간", default_value=10, time_count = "time")
    induce_time = listen_number(word = "복약 유도 시간", default_value=5, time_count = "time")

    save_config(user_id, dosage_time, dosage_count, meal_time, induce_time)