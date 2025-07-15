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
        subprocess.run(["aplay", "-D", speaker_device, temp_path], check=True)
    except Exception as e:
        print(f"에러 {e}")

# 마이크 찾는 함수
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

# 찾은 마이크의 인덱스 정보 저장 함수
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

# 마이크 정보 불러오는 함수
def load_mic_index():
    if os.path.exists(MIC_CONFIG_PATH):
        with open(MIC_CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("mic_index", None)
    return None


# 스피커 정보 저장 함수
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

# 스피커 정보 불러오는 함수
def load_speaker_device():
    if os.path.exists(SPEAKER_CONFIG_PATH):
        with open(SPEAKER_CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("speaker_device", "hw:0,0")
    return "hw:0,0"

import threading

def load_hw_device():
    if os.path.exists(MIC_CONFIG_PATH):
        with open(MIC_CONFIG_PATH, "r") as f:
            config = json.load(f)
            return config.get("hw_device", "hw:0,0")
    return "hw:0,0"
    
CONFIG_PATH = "/home/pi/my_project/config.py" 

# 사용자 정보 저장 함수
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
    
