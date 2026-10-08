# 🎙️ 살가이(SalGai) - AI 음성 기반 복약 알림 시스템

## 📋 프로젝트 개요

**살가이**는 15주간의 개발을 통해 구현된 라즈베리파이 기반의 AI 음성 어시스턴트입니다. STT, TTS, 그리고 LLM을 활용하여 사용자와 자연스러운 상호작용을 제공하며, 정해진 시간에 복약 알림을 전달합니다.

---

## 핵심 기능

### 1. 복약 알림 시스템

| 단계 | 시간차 | 내용 |
|------|--------|------|
| 식사 체크 | -10분 | "약 드시기 전에 식사하셨나요?" |
| 복약 유도 | -5분 | "약 드실 준비 되셨나요?" |
| 복약 알림 | 0분 | "약 드실 시간입니다" |
| 재알림 | +5분 | "약 드셨나요?" (최대 3회) |

### 2. 웨이크워드 기능

"살가이"라고 부르면 음성 명령 가능
- "다음 약은 언제야?" → "오후 1시 30분입니다"
- "오늘 약 스케줄이 뭐야?" → "아침 8시, 점심 12시, 저녁 6시"

엔진: Porcupine (90%+ 정확도, 저전력)

### 3. 음성 처리

사용자 음성 → 마이크 → 서버 STT → LLM → TTS → 스피커
전체 응답: ~24-30초

---

## 소프트웨어 구조

### Thread Lock 기반 마이크 자원 관리

#### 문제: 마이크 점유 충돌

2개 라이브러리가 동시에 마이크 접근:
- WakeWord: pvporcupine (pvaudio 사용) - 상시 리스닝
- STT: arecord (ALSA 사용) - 녹음 필요

결과: 마이크 자원 충돌 → 음성 인식 실패

#### 해결: Mutex (Thread Lock)

**1. 전역 Lock 정의** (global_state.py)
```python
import threading
mic_lock = threading.Lock()  # 마이크 자원 보호
```

**2. WakeWord에서 낮은 우선순위로 Lock 획득** (WakeWord.py)
```python
while True:
    if not mic_lock.acquire(timeout=0.1):  # 0.1초 타임아웃
        time.sleep(0.2)
        continue
    
    try:
        result = porcupine.process(pcm)
        if result >= 0:
            mic_lock.release()  # 중간에 마이크 해제
            return upload_stt()
    finally:
        mic_lock.release()
```

**3. STT에서 높은 우선순위로 Lock 보호** (RequestStt.py)
```python
def record_audio():
    with mic_lock:  # Context manager로 마이크 점유
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        while True:
            data = process.stdout.read(CHUNK_SIZE)
            rms = audioop.rms(data, 2)
            if rms < SILENCE_THRESHOLD:  # 3초 무음
                break
        process.kill()
        process.wait()
```

#### 작동 방식

시간 흐름:

WakeWord: [Lock] ──── [해제] ──── [Lock] ──── [해제]
          감지   0.1s 대기      감지   0.1s 대기
           |                     |
STT:               [Lock] ────────── [해제]
                   (음성 녹음)

동시 접근 방지, 한 번에 하나만 마이크 사용

#### 우선순위
- WakeWord: 0.1초 타임아웃으로 자주 마이크 해제 (복약 중에도 감지 가능)
- STT: Context manager로 완전히 마이크 보호 (온전한 음성 녹음)

---

## 문제 해결

### 1. 웨이크워드 감지 안 됨

원인: 3.5mm 마이크의 열악한 음성 신호
- 라즈베리파이와 호환성 낮음
- 실내 배경 노이즈가 음성 왜곡
- 음량 증폭 한계로 정규화 불충분

해결: USB 마이크로 교체
- 입력 신호 안정화
- 노이즈 상쇄 필터 적용
- 결과: 감지율 30-40% → 90%+

코드 (RequestStt.py):
```python
SILENCE_THRESHOLD = 1600  # 무음 기준
SILENCE_DURATION = 3      # 3초 무음 시 종료

rms = audioop.rms(data, 2)  # 실시간 음량 분석
if rms < SILENCE_THRESHOLD:
    if time.time() - silence_start > SILENCE_DURATION:
        break
```

### 2. 마이크 점유 충돌

원인: 복약 알림 루틴과 웨이크워드 감지가 동시에 마이크 접근

해결: Mutex (Thread Lock) 기반 동기화
- global_state.py: Lock 정의
- WakeWord.py: 낮은 우선순위 (0.1초 타임아웃)
- RequestStt.py: 높은 우선순위 (Context manager)

결과:
- 멀티스레드 환경에서 안정적 동작
- 녹음 중 데이터 손상 방지
- 웨이크워드 감지 중단 없음

---

## 성능 평가

응답 시간:
- STT: ~11초
- LLM: ~12초
- TTS: ~17초
- 전체: ~24-30초

마이크 감지:
- USB 마이크: 90%+
- 3.5mm 마이크: 30-40%

발열:
- 24시간 연속: 안정적 (48-49°C)

---

## 설치 및 실행

```bash
git clone https://github.com/xmflzhqxj/RaspberryPi-speaker.git
cd RaspberryPi-speaker
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
python3 main.py
```

---

개발자: KDH
개발 기간: 15주
라이센스: MIT

GitHub: https://github.com/xmflzhqxj/RaspberryPi-speaker
