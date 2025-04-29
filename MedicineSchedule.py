import os
import threading
import time
from collections import deque
from datetime import datetime
from datetime import time as dtime
from datetime import timedelta

import requests
from dateutil import parser

from config import (
    BASE_URL,
    DOSAGE_COUNT,
    DOSAGE_TIME,
    INDUCE_TIME,
    MEAL_TIME,
    USER_ID,
)
from llmTts import conversation_and_check, post_taking_medicine
from RequestStt import upload_stt
from RequestTts import text_to_voice

scheduled_times_set = set()
pending_alerts = deque()
ALARM_TOLERANCE_MINUTES = 2

def get_user_name(user_id):
    try:
        res = requests.get(f"{BASE_URL}/api/users")
        if res.status_code == 200:
            users = res.json().get("users_list", [])
            for user in users:
                if user["id"] == user_id:
                    return user["name"]
    except Exception as e:
        print(f"이름 조회 실패 {e}")
    return "사용자"

USER_NAME = get_user_name(USER_ID)

def medicine_alert(sched_dt: datetime, dosage_mg, schedule_id):
    alert = {
        "schedule_id": schedule_id,
        "scheduled_time": sched_dt.strftime("%H:%M"),
        "dosage_mg": dosage_mg,
        "retry_count": 0,
        "sched_dt": sched_dt,
        "steps": deque([
            {"offset": -MEAL_TIME, "responsetype": "check_meal", "message": f"{USER_NAME}님 약 드시기 {MEAL_TIME}분 전입니다. 약 드시기 전에 식사 하셨나요?"},
            {"offset": -INDUCE_TIME, "responsetype": "induce_medicine", "message": f"{USER_NAME}님 요 며칠 약 챙겨드시기 어려우셨죠?"},
            {"offset": 0, "responsetype": "taking_medicine_time"},
            {"offset": 0.1, "responsetype": "check_medicine", "message": f"{USER_NAME}님 약 {dosage_mg}mg 드실 시간이에요."},
        ])
    }
    pending_alerts.append(alert)
    print(f"복약 응답 대기중... 현재 {len(pending_alerts)}건")

def process_immediate_alert():
    now = datetime.now()
    for alert in list(pending_alerts):
        schedule_id = alert["schedule_id"]
        sched_dt = alert["sched_dt"]

        if not alert["steps"]:
            continue

        step = alert["steps"][0]
        target_time = sched_dt + timedelta(minutes=step["offset"])

        if now > target_time + timedelta(minutes=ALARM_TOLERANCE_MINUTES):
            alert["steps"].popleft()
            continue

        if now >= target_time:
            alert["steps"].popleft()
            try:
                if step["responsetype"] == "taking_medicine_time":
                    taking_medicine = post_taking_medicine(schedule_id, USER_ID)
                elif step["responsetype"] == "check_medicine":
                    # 사용자 녹음 -> 복약 여부 판단 -> 기록 전송
                    success = upload_stt()
                    if success:
                        result = conversation_and_check(
                            responsetype="check_medicine",
                            schedule_id=schedule_id,
                            user_id=USER_ID
                        )
                        if result:
                            taken_at = datetime.now().strftime("%y.%m.%d.%H.%M")
                            payload = {"schedule_id": schedule_id, "taken_at": taken_at}
                            try:
                                res = requests.put(f"{BASE_URL}/api/user/histories", json=payload)
                                if res.status_code == 200:
                                    print("복약 기록 전송 성공")
                                    pending_alerts.remove(alert)
                                else:
                                    print(f"전송 실패: {res.status_code} - {res.text}")
                            except Exception as e:
                                print(f"전송 에러: {e}")
                        else:
                            alert["retry_count"] += 1
                            if alert["retry_count"] > DOSAGE_COUNT:
                                pending_alerts.remove(alert)
                            else:
                                next_retry = {
                                "offset": DOSAGE_TIME,
                                "responsetype": "check_medicine",
                                "message": f"{USER_NAME}님 약 드셨나요?"
                                }
                                alert["steps"].appendleft(next_retry)
                    else:
                        print("STT 업로드 실패")
                        text_to_voice("음성 인식에 실패했습니다. 다시 말씀해 주세요.")
                else:
                    text_to_voice(step["message"])
                    success = upload_stt()
                    if success:
                        result = conversation_and_check(
                            responsetype=step["responsetype"],
                            schedule_id=schedule_id,
                            user_id=USER_ID
                        )
                    else:
                        text_to_voice("음성 인식에 실패했습니다. 다시 한번 말씀해 주세요.")
            except Exception as e:
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
            return today_schedule
        else:
            print(f"get 서버 응답 오류 : {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"get 서버 요청 실패: {e}")
        return []

def register_schedule(schedule_list):
    now = datetime.now().replace(second=0, microsecond=0)
    schedule_list.sort(key=lambda r: datetime.fromisoformat(r["scheduled_time"]))
    for record in schedule_list:
        sched_dt = datetime.fromisoformat(record["scheduled_time"]).replace(second=0, microsecond=0)

        dosage_mg = record["dosage_mg"]
        schedule_id = record["id"]
        unique_key = f"{schedule_id}_{sched_dt.strftime('%Y-%m-%d %H:%M')}"

        if unique_key in scheduled_times_set:
            continue

        if sched_dt < now:
            continue
        medicine_alert(
            sched_dt=sched_dt,
            dosage_mg=dosage_mg,
            schedule_id=schedule_id
        )
        scheduled_times_set.add(unique_key)

    process_immediate_alert()

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
    while True:
        time.sleep(60)

def daily_refresh():
    print(f"[{datetime.now()}] 자정 이후 알람 새로고침")
    scheduled_times_set.clear()
    schedule_list = get_today_schedule()
    register_schedule(schedule_list)

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

if __name__ == "__main__":
    run_scheduler()