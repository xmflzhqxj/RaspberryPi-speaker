import threading
import time
from collections import deque
from datetime import datetime
from datetime import time as dtime
from datetime import timedelta

import requests
import schedule
from dateutil import parser

from config import (
    BASE_URL,
    DOSAGE_COUNT,
    DOSAGE_TIME,
    INDUCE_TIME,
    MEAL_TIME,
    USER_ID,
    WAV_PATH,
)
from llmTts import conversation_and_check
from RequestStt import upload_stt
from RequestTts import text_to_voice

scheduled_times_set = set()
pending_alerts = deque()

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

def medicine_alert(scheduled_time, dosage_mg, schedule_id):
    alert = {
        "schedule_id": schedule_id,
        "scheduled_time": scheduled_time,
        "dosage_mg": dosage_mg,
        "steps": deque([
            {"offset": -MEAL_TIME, "responsetype": "check_meal", "message": f"{USER_NAME}님 약먹기 {MEAL_TIME}분 전입니다. 식사 하셨나요?"},
            {"offset": -INDUCE_TIME, "responsetype": "induce_medicine", "message": f"{USER_NAME}님 약먹기 {INDUCE_TIME}분 전입니다."},
            {"offset": 0, "responsetype": "check_medicine", "message": f"{USER_NAME}님 약 {dosage_mg}mg 먹을 시간이에요."},
        ])
    }
    pending_alerts.append(alert)
    print(f"복약 응답 대기중... 현재 {len(pending_alerts)}건")

def input_loop():
    while True:
        now = datetime.now()

        for alert in list(pending_alerts):
            schedule_id = alert["schedule_id"]
            scheduled_time = alert["scheduled_time"]
            dosage_mg = alert["dosage_mg"]

            # 기본값 설정 (없으면 0으로)
            alert.setdefault("retry_count", 0)

            sched_dt = datetime.combine(
                now.date(), 
                dtime(
                    int(scheduled_time.split(":")[0]),
                    int(scheduled_time.split(":")[1])
                )
            )

            if not alert["steps"]:
                #retry 스텝이 추가되어 있는 경우
                if alert.get("retry_count", 0) == 0:
                    pending_alerts.remove(alert)
                else:
                    print(f"복약 재시도 예정 (retry_count={alert['retry_count']})")

            step = alert["steps"][0]
            target_time = sched_dt + timedelta(minutes=step["offset"])

            if now > target_time + timedelta(minutes=2) :
                alert["steps"].popleft()
                continue

            if now >= target_time:
                step = alert["steps"].popleft()

                try:
                    text_to_voice(step["message"])
    
                    success = upload_stt()
                    if success:
                        result = conversation_and_check(
                            WAV_PATH,
                            responsetype=step["responsetype"],
                            schedule_id=schedule_id,
                            user_id=USER_ID
                        )

                        if step["responsetype"] == "check_medicine":
                            if result:
                                taken_at = datetime.now().strftime("%y.%m.%d.%H.%M")
                                payload = {"schedule_id": schedule_id, "taken_at": taken_at}
                                print(f"복약 기록 전송중...(ID: {schedule_id})")
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
                                # 복약 실패 -> 재알림
                                alert["retry_count"] += 1
                                if alert["retry_count"] > DOSAGE_COUNT:
                                    print(f"복약 실패로 알람 삭제 (ID: {schedule_id})")
                                    pending_alerts.remove(alert)
                                else:
                                    print(f"{DOSAGE_TIME}분 후 재알림 예정 (재시도 {alert['retry_count']}회)")
                                    next_retry = {
                                        "offset": -(DOSAGE_TIME * alert["retry_count"]),
                                        "responsetype": "check_medicine",
                                        "message": f"{USER_NAME}님 약 {dosage_mg}mg 드셨나요?)"
                                    }
                                    alert["steps"].appendleft(next_retry)

                        else:
                            text_to_voice(result)

                    else:
                        print("STT 업로드 실패")
                        text_to_voice("음성 인식에 실패했습니다. 다시 한번 말씀해 주세요.")

                except Exception as e:
                    print(f"스텝 처리 중 오류: {e}")

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
        if sched_dt <= now:
            continue

        time_str = sched_dt.strftime("%H:%M")
        dosage_mg = record["dosage_mg"]
        schedule_id = record["id"]
        unique_key = f"{schedule_id}_{sched_dt.strftime('%Y-%m-%d %H:%M')}"

        if unique_key not in scheduled_times_set:
            schedule.every().day.at(time_str).do(
                medicine_alert,
                scheduled_time=time_str,
                dosage_mg=dosage_mg,
                schedule_id=schedule_id
            )
            scheduled_times_set.add(unique_key)
            print(f"알람 등록 : {unique_key}, 용량 : {dosage_mg}mg")

            if sched_dt == now:
                medicine_alert(
                    scheduled_time=time_str,
                    dosage_mg=dosage_mg,
                    schedule_id=schedule_id
                )

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
    print("복용알람 진행중...")

    schedule.every().day.at("00:00").do(daily_refresh)
    threading.Thread(target=input_loop, daemon=True).start()

    while True:
        schedule.run_pending()
        time.sleep(1)

def daily_refresh():
    print(f"[{datetime.now()}] 자정 이후 알람 새로고침")
    schedule.clear()
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
