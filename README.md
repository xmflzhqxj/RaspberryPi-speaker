# 🎙️ 살가이(SalGai) - AI 음성 기반 복약 알림 시스템

> 라즈베리파이 기반의 AI 음성 인식 복약 알림 시스템으로, 사용자의 음성 명령을 인식하고 특정 시간에 복약을 알려주는 스마트 헬스케어 디바이스입니다.

## 📋 프로젝트 개요

**살가이**는 15주간의 개발을 통해 구현된 라즈베리파이 기반의 AI 음성 어시스턴트입니다. STT(Speech-to-Text), TTS(Text-to-Speech), 그리고 LLM을 활용하여 사용자와 자연스러운 상호작용을 제공하며, 정해진 시간에 복약 알림을 전달합니다.

### 📊 프로젝트 타임라인
- **개발 기간**: 15주 (풀타임 개발)
- **목표 달성도**: 100%
- **프로토타입 출고**: 완료

---

## 🏗️ 시스템 아키텍처

### 주요 구성 요소

```
┌─────────────────────────────────────────────────┐
│  Raspberry Pi 5 (메인 프로세서)                  │
│  ┌───────────────────────────────────────────┐  │
│  │ 병렬 실행 (2개 Thread)                     │  │
│  │ ├─ 복약 알림 루틴 (스케줄러)              │  │
│  │ └─ 웨이크워드 감지 (Porcupine)           │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
    ↓                ↓                 ↓
  마이크          LLM 서버          GPIO
  (STT)       (의도 판단/TTS)    (LED, 버튼)
```

---

## ✨ 핵심 기능

### 1️⃣ **복약 알림 시스템**

#### 단계별 알림 프로세스

| 단계 | 시간차 | 내용 | 사용자 응답 |
|------|--------|------|-----------|
| 식사 체크 | -10분 | "약 드시기 전에 식사하셨나요?" | 음성 응답 |
| 복약 유도 | -5분 | "약 드실 준비 되셨나요?" | 음성 응답 |
| **복약 알림** | **0분** | **"약 드실 시간입니다"** | **버튼/살가이** |
| 재알림 | +5분 | "약 드셨나요?" | 음성 (최대 3회) |

**미복약 처리**
- 규정 시간 이후 자동 미복약 처리
- 자동 재알림: 30분 간격 최대 6회
- 사용자 맞춤 설정 가능

### 2️⃣ **웨이크워드 기능**

#### "살가이" 음성 명령
사용자가 "살가이"라고 부르면 음성으로 명령 가능:

```
사용자: "살가이! 다음 약은 언제야?"
→ AI: "오후 1시 30분입니다."

사용자: "살가이! 오늘 약 스케줄이 뭐야?"
→ AI: "아침 8시, 점심 12시, 저녁 6시입니다."
```

**웨이크워드 감지 엔진**: Porcupine
- ✅ 오프라인 동작
- ✅ 저전력 (라즈베리파이 최적화)
- ✅ 높은 정확도 (90%+)

### 3️⃣ **음성 처리 파이프라인**

```
사용자 음성
    ↓
마이크 녹음 (arecord)
    ↓
서버 전송 (API)
    ↓
STT (음성 → 텍스트)
    ↓
LLM (의도 판단)
    ↓
TTS (텍스트 → 음성)
    ↓
스피커 재생
```

**성능 지표**
- STT: ~11초 (녹음 10초 + 서버 처리 1초)
- LLM: ~12초
- TTS: ~17초
- **전체 응답: ~24-30초**

---

## 🔧 하드웨어 구성

### 필수 장치

| 항목 | 모델 | 가격 | 용도 |
|------|------|------|------|
| 메인보드 | Raspberry Pi 5 | $50-80 | 프로세서 |
| 마이크 | KLIM Talk USB | $20.97 | 음성 입력 |
| 스피커 | S150 USB Stereo | $17.99 | 음성 출력 |
| LED | RGB LED (5mm) | 저가 | 상태 표시 |
| 버튼 | 푸시 버튼 | 저가 | 사용자 입력 |

### GPIO 핀 할당

```python
RED_LED = 17      # 음성 녹음 중
BLUE_LED = 27     # 대기 중 (웨이크워드 리스닝)
GREEN_LED = 22    # LLM 처리 중
YELLOW_LED = 24   # 에러 상태

BUTTON = 23       # 복약 확인
SKIP_SWITCH = 25  # 시간 건너뛰기
RESET_SWITCH = 26 # 프로그램 재시작
```

### 하드웨어 성능

**발열 테스트**
- 부팅 직후: 42~47°C (정상)
- 6시간 연속 운영: 47°C (안정)
- 12시간 연속 운영: 48~49°C (안정)
- 24시간 연속 운영: 안정적 ✅

**부팅 시간**
- 라즈베리파이 부팅: ~15초
- 코드 초기화: ~10초
- **총 준비 시간: 25-30초**

---

## 💻 소프트웨어 구조

### 핵심 파일

```
├── main.py                  # 프로그램 진입점
├── MedicineSchedule.py      # 복약 알림 로직
├── WakeWord.py             # 웨이크워드 감지
├── RequestStt.py           # STT 처리
├── RequestTts.py           # TTS 처리
├── llmTts.py               # LLM 통합
├── gpio_controller.py      # GPIO 제어
├── util.py                 # 유틸리티 함수
└── requirements.txt        # 의존성
```

### 주요 기술

**Thread Lock 기반 마이크 자원 관리**
```python
mic_lock = threading.Lock()

# 웨이크워드 (우선순위 높음)
def wakeword():
    if not mic_lock.acquire(timeout=0.1):
        return
    # 웨이크워드 처리

# STT (우선순위 낮음)
def record_audio():
    with mic_lock:  # 웨이크워드 완료 후 실행
        # 음성 녹음
```

---

## 🚀 설치 및 실행

### 전제 조건
- Raspberry Pi 5 (Pi 4+ 호환)
- Ubuntu/Debian OS
- Python 3.8+

### 설치 단계

#### 1️⃣ 저장소 클론
```bash
git clone https://github.com/xmflzhqxj/RaspberryPi-speaker.git
cd RaspberryPi-speaker
```

#### 2️⃣ 가상 환경 및 의존성 설치
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

#### 3️⃣ 설정 파일 수정
```python
# config.py
BASE_URL = "http://YOUR_API_SERVER:8000"
USER_ID = 1
```

#### 4️⃣ 프로그램 실행
```bash
python3 main.py
```

---
<<<<<<< HEAD

## 📊 개발 과정 (주차별 요약)

### 1주차: STT 초기 테스트
- speech_recognition 라이브러리 테스트
- 정확도: ~60%

### 2주차: TTS 및 하드웨어 선정
- gTTS 선택 (자연스러운 음성)

### 3주차: 복약 알림 프로토타입
- 마이크/스피커 성능 분석
- API 연동 테스트

### 4주차: 복약 알림 확대
- ✅ 자정 알람
- ✅ 미복약 처리
- ✅ 음성 응답 인식

### 5주차: STT/TTS 최적화
- 반응 시간 단축

### 6주차: 시스템 안정화
- LLM 통합

### 7주차: 부팅 및 자동 실행
- Systemd 서비스 등록

### 8주차: 음성 녹음 개선
- 자동 종료 감지

### 9주차: AI 대화 기능
- 식사 체크
- 복약 유도
- 복약 확인

### 10주차: 하드웨어 추가
- LED 상태 표시
- 버튼 입력

### 11주차: 통합 테스트
- 마이크 충돌 해결 (Thread Lock)
- 웨이크워드 우선순위

### 12주차: 웨이크워드 우선 감지
- 복약 루틴 중 웨이크워드 처리

### 13-15주차: 테스트 및 최적화
- 실사용 환경 테스트
- 최종 제품 출고

---

## 🎓 주요 기술 결정사항

### 1. 웨이크워드 엔진: Porcupine ✅

| 특징 | Porcupine | Vosk | Snowboy |
|------|-----------|------|---------|
| 리소스 | 매우 적음 | 많음 | 적음 |
| 라즈베리파이 최적 | ✅ | ❌ | ❌ |
| 정확도 | 90%+ | 70% | 75% |

### 2. STT/TTS 아키텍처

**개선**: 라즈베리파이 → 서버 분산
- 라즈베리파이: 녹음/재생만
- 서버: STT, LLM, TTS
- 결과: 응답 시간 30초 → 24초 (20% 개선)

### 3. 마이크 자원 충돌 해결

**해결**: Thread Lock 기반 자원 관리
- 웨이크워드가 우선순위 높음
- 마이크를 Lock으로 보호
- 동시 접근 방지

---

## 📈 성능 평가

### 응답 시간
- STT: ~11초
- LLM: ~12초
- TTS: ~17초
- **전체**: ~24-30초

### 마이크 감지
- USB 마이크: 90%+
- 3.5mm 마이크: 30-40%

### 발열 관리
- 24시간 연속: 안정적 ✅

---

## 🐛 주요 문제 해결 사례

### 문제 1: 웨이크워드 감지 안 됨

#### 목표
- 사용자가 "살가이"라고 부르면 즉시 반응
- 90%+ 정확도로 안정적인 감지

#### 발생한 문제

**원인**:
- 3.5mm 마이크는 라즈베리파이와의 호환성이 낮음
- 실내 배경 노이즈가 음성 신호를 왜곡
- 마이크의 음량 증폭 한계로 정규화 불충분
- **결과**: 웨이크워드 감지율 30-40% (실패)

#### 해결 방법

**변경사항**:
- 3.5mm 마이크 → USB 마이크 (KLIM Talk) 교체
- 더 안정적인 입력 신호 확보

**코드 개선** (RequestStt.py):
```python
import audioop

SILENCE_THRESHOLD = 1600  # 무음 기준 (RMS 값)
SILENCE_DURATION = 3      # 3초 무음 시 녹음 종료

def record_audio():
    with mic_lock:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        frames = []
        silence_start = None

        while True:
            data = process.stdout.read(CHUNK_SIZE)
            frames.append(data)
            
            # 실시간 음량 분석 (RMS)
            rms = audioop.rms(data, 2)

            # 무음 감지 로직
            if rms < SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > SILENCE_DURATION:
                    print("말이 멈췄다고 판단됨. 녹음 종료.")
                    break
            else:
                silence_start = None

        process.kill()
        process.wait()
```

**결과**: ✅ 감지율 30-40% → **90%+로 개선**

---

### 문제 2: 마이크 점유 충돌

#### 목표
- 웨이크워드 감지와 STT 녹음이 동시에 안정적으로 동작
- 멀티스레드 환경에서 마이크 자원 충돌 방지

#### 발생한 문제

**원인**:
- 복약알람 루틴과 음성 인식 루틴이 동시에 마이크에 접근
- 라즈베리파이의 하드웨어 자원이 제한적
- 두 라이브러리가 경쟁하면서 음성 신호 손상
- **결과**: 음성 인식 실패 또는 프로그램 크래시

#### 해결 방법

**Mutex (Thread Lock) 기반 동기화**

**1. 전역 Lock 정의** (global_state.py):
```python
import threading

pending_alerts = deque()
mic_lock = threading.Lock()  # 마이크 자원 보호
wakeword_detection = False
```

**2. STT에서 높은 우선순위로 Lock 점유** (RequestStt.py):
```python
from global_state import mic_lock

def record_audio():
    with mic_lock:  # Context manager로 완전 보호
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        # 음성 녹음 처리...
```

**3. WakeWord에서 낮은 우선순위로 Lock** (WakeWord.py):
```python
from global_state import mic_lock

def listen_for_wakeword():
    while True:
        if not mic_lock.acquire(timeout=0.1):
            time.sleep(0.2)
            continue

        try:
            result = porcupine.process(pcm)
            if result >= 0:
                mic_lock.release()
                return upload_stt()
        finally:
            mic_lock.release()
```

**결과**: 
- ✅ 멀티스레드 환경에서 안정적 동작
- ✅ 녹음 중 데이터 손상 방지
- ✅ 웨이크워드 감지 중단 없음

---

## 📚 핵심 라이브러리

```
pvporcupine==3.0.0      # 웨이크워드
requests==2.31.0        # API 요청
pydub==0.25.1           # 오디오 처리
RPi.GPIO==0.7.0         # GPIO 제어
schedule==1.2.0         # 작업 스케줄
```

---

=======
