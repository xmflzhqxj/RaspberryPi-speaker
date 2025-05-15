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
    INDUCE_TIME,
    MEAL_TIME,
    USER_ID,
    FE_USER_ID
)
from global_state import pending_alerts
from gpio_controller import GPIOController
from llmTts import conversation_and_check, post_taking_medicine
from RequestStt import upload_stt
from RequestTts import text_to_voice
from util import auto_save_mic, auto_save_speaker, wait_for_microphone

gpio = GPIOController(refresh_callback=lambda: on_button_press())
atexit.register(gpio.cleanup)

scheduled_times_set = set()
ALARM_TOLERANCE_MINUTES = 1
MAX_CONFIRMATION_WAIT = DOSAGE_TIME 

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
            {"offset": -INDUCE_TIME, "responsetype": "induce_medicine", "message": f"{USER_NAME}님 요 며칠 약 챙겨드시기 어려우셨죠?"},
            {"offset": 0, "responsetype": "taking_medicine_time"},
            {"offset": DOSAGE_TIME, "responsetype": "check_medicine", "message": f"{USER_NAME}님 약 {dosage_mg}mg 드셨나요 ?"},
        ])
    }
    pending_alerts.append(alert)
    print(f"복약 응답 대기중... 현재 {len(pending_alerts)}건")

def process_immediate_alert():
    now = datetime.now()
    
    for alert in list(pending_alerts):
        if not alert["steps"]:
            continue

        step = alert["steps"][0]
        target_time = alert["sched_dt"] + timedelta(minutes=step["offset"])

        if now > target_time + timedelta(minutes=ALARM_TOLERANCE_MINUTES):
            alert["steps"].popleft()
            continue

        if now >= target_time:
            alert["steps"].popleft()
            try:
                if step["responsetype"] == "taking_medicine_time":
                    post_taking_medicine(DUMMY_ID, FE_USER_ID)
                    alert["wait_for_confirmation"] = True
                    alert["confirmation_started_at"] = datetime.now()
                    return  
                
                print(step["message"])
                text_to_voice(step["message"])
                
                user_response = upload_stt()

                if user_response:
                    result = conversation_and_check(
                        responsetype=step["responsetype"],
                        schedule_id=alert["schedule_id"],
                        user_id=FE_USER_ID
                    )
                    if step["responsetype"] == "check_medicine":
                        if result:
                            handle_medicine_confirmation(alert)
                        else:
                            alert["retry_count"] += 1
                            if alert["retry_count"] < DOSAGE_COUNT:
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

                
def input_loop():
    while True:
        process_immediate_alert()
        time.sleep(0.5)

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

    threading.Thread(target=refresh_loop, daemon=True).start()

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

def on_button_press():
    refresh_schedules_now()
    now = datetime.now()
    for alert in list(pending_alerts):
        if alert.get("wait_for_confirmation"):
            elapsed = (now - alert["confirmation_started_at"]).total_seconds() / 60
            if elapsed <= MAX_CONFIRMATION_WAIT:
                handle_medicine_confirmation(alert)  
                return

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

def get_next_medicine_info():
    schedule_list = get_today_schedule()
    now = datetime.now()
    for record in sorted(schedule_list, key=lambda r: r["scheduled_time"]):
        sched_time = datetime.fromisoformat(record["scheduled_time"])
        if sched_time > now:
            time_str = sched_time.strftime("%p %I시 %M분").replace("AM", "오전").replace("PM", "오후")
            dosage_mg = record["dosage_mg"]
            return f"{USER_NAME}님의 다음 약은 {time_str}에 {dosage_mg}밀리그램 만큼 드셔야 합니다."
    return "오늘 남은 약이 없습니다."

def get_today_schedule_summary():
    schedule_list = get_today_schedule()
    if not schedule_list:
        return f"{USER_NAME}님의 오늘 복약 스케줄이 없습니다."
    summary = f"{USER_NAME}님의 오늘 복약 스케줄은 다음과 같습니다."
    for r in sorted(schedule_list, key=lambda r: r["scheduled_time"]):
        sched_time = datetime.fromisoformat(r["scheduled_time"])
        time_str = sched_time.strftime("%p %I시 %M분").replace("AM", "오전").replace("PM", "오후")
        summary += f" {time_str}에 {r['dosage_mg']}밀리그램,"
    return summary.strip(" ,")

def handle_command(text):
    for cmd in command_patterns:
        if re.search(cmd["pattern"], text):
            if cmd["responsetype"] == "next_medicine":
                return get_next_medicine_info()
            elif cmd["responsetype"] == "today_schedule":
                return get_today_schedule_summary()  

# from WakeWord import wakeWord_once

# def wakeword_medicine_check(alert):
#     max_wait = MAX_CONFIRMATION_WAIT * 60  # seconds
#     start_time = time.time()

#     while mic_lock.locked():
#         print("마이크 점유 중 → wakeword 대기")
#         time.sleep(0.5)

#     while time.time() - start_time < max_wait:
#         result_text = wakeWord_once() # 이때만 wake word 켜기
#         if result_text:
#             is_taken = conversation_and_check(
#                 responsetype="check_medicine",
#                 schedule_id=alert["schedule_id"],
#                 user_id=USER_ID
#             )
#             if is_taken:
#                 handle_medicine_confirmation(alert)
#                 break
#         time.sleep(1)

if __name__ == "__main__":
    if wait_for_microphone():
        time.sleep(2)
        auto_save_mic()
        auto_save_speaker()
    else:
        print("마이크를 찾을 수 없습니다.")

    run_scheduler()
