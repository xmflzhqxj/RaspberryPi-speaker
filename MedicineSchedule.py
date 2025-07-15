import atexit
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta

import requests
from dateutil import parser

from commandHandler import command_patterns
from config import (
    BASE_URL,
    DOSAGE_COUNT,
    DOSAGE_TIME,
    DUMMY_ID,
    FE_USER_ID,
    INDUCE_TIME,
    MEAL_TIME,
    USER_ID,
)
from global_state import pending_alerts # 정해진 루틴이 있으므로 Queue 설정
from gpio_controller import GPIOController
from llmTts import conversation_and_check, post_taking_medicine
from RequestStt import upload_stt
from RequestTts import text_to_voice
from util import auto_save_mic, auto_save_speaker, wait_for_microphone

gpio = GPIOController(refresh_callback=lambda: on_button_schedule())
atexit.register(gpio.cleanup)

scheduled_times_set = set() 
ALARM_TOLERANCE_MINUTES = 1
MAX_CONFIRMATION_WAIT = DOSAGE_TIME 

# 사용자 이름 가져오는 함수
def get_user_name(user_id):
    try:
        res = requests.get(f"{BASE_URL}/api/users")
        if res.status_code == 200:
            users = res.json().get("users_list", [])
            for user in users:
                if user["id"] == user_id:
                    return user["name"]
    except Exception as e:
        print(f"이름 조회 실패: {e}")
        gpio.set_mode("error")
    return "사용자"

USER_NAME = get_user_name(USER_ID)

# 복약 정보 함수
def medicine_alert(sched_dt: datetime, dosage_mg, schedule_id):
    alert = {
        "schedule_id": schedule_id,
        "scheduled_time": sched_dt.strftime("%H:%M"),
        "dosage_mg": dosage_mg,
        "retry_count": 0,
        "sched_dt": sched_dt,
        "wait_for_confirmation": False,
        "confirmation_started_at": 0,
        "steps": deque([
            {"offset": -MEAL_TIME, "responsetype": "check_meal", "message": f"{USER_NAME}님 약 드시기 {MEAL_TIME}분 전입니다. 약 드시기 전에 식사 하셨나요?"},
            # {"offset": -INDUCE_TIME, "responsetype": "induce_medicine", "message": f"{USER_NAME}님 요 며칠 약 챙겨드시기 어려우셨죠?"},
            {"offset": 0, "responsetype": "taking_medicine_time"},
            {"offset": DOSAGE_TIME, "responsetype": "check_medicine", "message": f"{USER_NAME}님 약 {dosage_mg}mg 드셨나요 ?"},
        ])
    }
    pending_alerts.append(alert)
    print(f"복약 응답 대기중... 현재 {len(pending_alerts)}건")

# 스텝 처리
def process_step(alert, step):
    try:
        if step["responsetype"] == "taking_medicine_time": # 복약시간 
            post_taking_medicine(DUMMY_ID, FE_USER_ID)
            alert["wait_for_confirmation"] = True
            alert["confirmation_started_at"] = datetime.now()
            return

        print(step["message"])
        text_to_voice(step["message"])

        user_response = upload_stt() # 사용자 음성 녹음
        if user_response:
            result = conversation_and_check(
                responsetype=step["responsetype"],
                schedule_id=alert["schedule_id"],
                user_id=FE_USER_ID
            )
            if step["responsetype"] == "check_medicine": # 복약여부 재체크
                if result:
                    handle_medicine_confirmation(alert)
                else:
                    alert["retry_count"] += 1
                    if alert["retry_count"] < DOSAGE_COUNT: # 재알림
                        print(f"복약 실패 → {DOSAGE_TIME}분 후 재시도 예정 ({alert['retry_count']}/{DOSAGE_COUNT})")
                        alert["sched_dt"] = datetime.now()
                        alert["steps"].appendleft({
                            "offset": DOSAGE_TIME,
                            "responsetype": "check_medicine",
                            "message": f"{USER_NAME}님 약 {alert['dosage_mg']}mg 드셨나요 ?"
                        })
                    else:
                        print("최대 복약 재시도 초과로 알림 제거")
                        pending_alerts.remove(alert)
        else:
            text_to_voice("음성 인식에 실패했습니다.")
            gpio.set_mode("error")
    except Exception as e:
        gpio.set_mode("error")
        print(f"스텝 처리 중 오류: {e}")

# 복약 시간 처리 함수
def process_immediate_alert():
    now = datetime.now()
    
    for alert in list(pending_alerts):
        if not alert["steps"]:
            continue

        step = alert["steps"][0]
        target_time = alert["sched_dt"] + timedelta(minutes=step["offset"])

        if now > target_time + timedelta(minutes=ALARM_TOLERANCE_MINUTES): # 시간이 지나면 큐에서 해당 알람 제거
            alert["steps"].popleft()
            continue

        if now >= target_time:
            alert["steps"].popleft()
            process_step(alert, step)

# 알람 무한루프 함수
def input_loop():
    while True:
        process_immediate_alert()
        time.sleep(0.5)

# 당일 복약 스케줄 가져오는 함수
def get_today_schedule():
    url = f"{BASE_URL}/api/user/histories?user_id={USER_ID}"
    today_schedule = []
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            records = data.get("medication record", [])
            today = datetime.now().date()
            for r in records:
                try:
                    sched_dt = datetime.fromisoformat(r["scheduled_time"])
                    if sched_dt.date() == today:
                        today_schedule.append(r)
                except Exception as parse_err:
                    print(f"파싱 실패: {r['scheduled_time']} {parse_err}")
                    gpio.set_mode("error")
            return today_schedule
        else:
            print(f"GET 서버 응답 오류: {response.status_code} - {response.text}")
            gpio.set_mode("error")
            return []
    except Exception as e:
        print(f"GET 서버 요청 실패: {e}")
        gpio.set_mode("error")
        return []

# 스케줄 등록 함수
def register_schedule(schedule_list):
    now = datetime.now().replace(second=0, microsecond=0)
    schedule_list.sort(key=lambda r: datetime.fromisoformat(r["scheduled_time"]))
    for record in schedule_list:
        sched_dt = datetime.fromisoformat(record["scheduled_time"]).replace(second=0, microsecond=0)
        unique_key = f"{record['id']}_{sched_dt.strftime('%Y-%m-%d %H:%M')}"

        if unique_key in scheduled_times_set or sched_dt < now:
            continue

        medicine_alert(sched_dt, record["dosage_mg"], record["id"])
        scheduled_times_set.add(unique_key)

    process_immediate_alert()

# 복약알람 자정 새로고침 함수
def daily_refresh():
    def refresh_loop():
        while True:
            now = datetime.now()
            next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_seconds = (next_midnight - now).total_seconds()
            time.sleep(wait_seconds)

            print(f"[{datetime.now()}] 자정 이후 알람 새로고침")
            scheduled_times_set.clear()
            schedule_list = get_today_schedule()
            register_schedule(schedule_list)

    threading.Thread(target=refresh_loop, daemon=True).start() # 새로운 thread로 자정 판단 동시 진행

# 복약 새로고침 함수 
def refresh_schedules_now():
    text_to_voice(f"스케줄 새로고침")
    schedule_list = get_today_schedule()
    
    if schedule_list:
        print("오늘 복약 스케줄 !")
        for r in sorted(schedule_list, key=lambda r: r["scheduled_time"]):
            sched_time = parser.isoparse(r["scheduled_time"])
            print(f"  - {sched_time.strftime('%H:%M')} | {r['dosage_mg']}mg")
    else:
        print("오늘 복약 스케줄이 없습니다.")

    register_schedule(schedule_list)

# 버튼 누를 때 작동하는 함수 
def on_button_schedule():
    refresh_schedules_now() # 새로고침
    now = datetime.now()

    for alert in list(pending_alerts):
        if not alert["steps"]:
            continue

        if alert.get("wait_for_confirmation"): # 복약 처리 
            elapsed = (now - alert["confirmation_started_at"]).total_seconds() / 60
            if elapsed <= MAX_CONFIRMATION_WAIT:
                print("복약 확인 처리")
                handle_medicine_confirmation(alert)
                return

# 오늘 복약 스케줄 함수 
def run_scheduler():
    schedule_list = get_today_schedule()
    if schedule_list:
        print("오늘 복약 스케줄!")
        for r in sorted(schedule_list, key=lambda r: r["scheduled_time"]):
            sched_time = parser.isoparse(r["scheduled_time"])
            print(f"  - {sched_time.strftime('%H:%M')} | {r['dosage_mg']}mg")
    else:
        print("오늘 복약 스케줄이 없습니다.")

    register_schedule(schedule_list)
    threading.Thread(target=input_loop, daemon=True).start()
    daily_refresh()

    while True:
        time.sleep(60)

# 복약 기록 전송 함수 
def handle_medicine_confirmation(alert):
    taken_at = datetime.now().strftime("%y.%m.%d.%H.%M")
    payload = {"schedule_id": alert["schedule_id"], "taken_at": taken_at}
    try:
        res = requests.put(f"{BASE_URL}/api/user/histories", json=payload)
        if res.status_code == 200:
            text_to_voice("복약 기록 전송 성공")
            pending_alerts.remove(alert)
        else:
            print(f"전송 실패: {res.status_code} - {res.text}")
            gpio.set_mode("error")
    except Exception as e:
        print(f"전송 에러: {e}")
        gpio.set_mode("error")

if __name__ == "__main__":
    if wait_for_microphone():
        time.sleep(2)
        auto_save_mic()
        auto_save_speaker()
    else:
        print("마이크를 찾을 수 없습니다.")

    run_scheduler()
