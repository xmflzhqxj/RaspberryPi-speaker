import threading
import time
from collections import deque
from datetime import datetime, timedelta

import requests
import schedule
from dateutil import parser

from llmTts import check_taken_llm
from RequestStt import upload_stt
from RequestTts import text_to_voice

# 등록된 알람 중복 방지
scheduled_times_set = set()
USER_ID = 1 # 현재 사용자
base_url = "http://3.34.179.85:8000"
wav_path = "/home/pi/my_project/stt.wav"
DOSAGE_TIME = 5 #원래는 30분간격 -> 현재는 테스트를 위해 5분
DOSAGE_COUNT = 3 # 반복 횟수
pending_alerts = deque() # 응답 대기 중인 복약 스케줄 저장

def get_user_name(user_id):
    try:
        res = requests.get(f"{base_url}/api/users")
        if res.status_code == 200:
            users = res.json().get("users_list",[])
            for user in users:
                if user["id"] == user_id:
                    return user["name"]
    except Exception as e:
        print(f"이름 조회 실패 {e}")
    return "사용자"

USER_NAME = get_user_name(USER_ID)

def morning(user_name):
    print("아침약 음성 재생 중..")
    text_to_voice(f"{user_name}님, 아침약 드실 시간입니다.")

def afternoon(user_name):
    print("점심약 음성 재생 중..")
    text_to_voice(f"{user_name}님, 점심약 드실 시간입니다.")

def evening(user_name):
    print("저녁약 음성 재생 중..")
    text_to_voice(f"{user_name}님, 저녁약 드실 시간입니다.")

def play_alert_voice(scheduled_time):
	hour = int(scheduled_time.split(":")[0])
	if hour < 12:
		morning(USER_NAME)
	elif hour < 17:
		afternoon(USER_NAME)
	else:
		evening(USER_NAME)

def medicine_alert(scheduled_time, dosage_mg,schedule_id):
	alert = {
		"schedule_id": schedule_id,
		"scheduled_time":scheduled_time,
		"dosage_mg":dosage_mg,
		"start_time":datetime.now(),
		"next_alert_time":datetime.now() + timedelta(minutes=5),
		"alert_count":1
	}
	pending_alerts.append(alert)
	print(f"복약 응답 대기중... 현재 {len(pending_alerts)}건")

def input_loop():
    while True:
        if pending_alerts:
            now = datetime.now()

            for alert in list(pending_alerts):
                schedule_id = alert["schedule_id"]
                scheduled_time = alert["scheduled_time"]
                dosage_mg = alert["dosage_mg"]
                start_time = alert["start_time"]
                alert_count = alert.get("alert_count", 1)
                next_alert_time = alert.get("next_alert_time", start_time + timedelta(minutes=DOSAGE_TIME))

                elapsed_minutes = (now - start_time).total_seconds() / 60

                # DOSAGE_TIME*DOSAGE_COUNT 후 미복용 처리
                if elapsed_minutes > DOSAGE_TIME * DOSAGE_COUNT :
                    print(f"{DOSAGE_TIME*DOSAGE_COUNT}분 경과로 미복용 처리ㅣ : {scheduled_time}, {dosage_mg}mg (ID: {schedule_id})")
                    pending_alerts.remove(alert)
                    continue

                # DOSAGE_TIME만큼 재알림
                if(now >= next_alert_time and alert_count <= DOSAGE_COUNT) or alert_count == 1:
                    print(f"[{'초기알림' if alert_count == 1 else '재알림'}] 복약시간입니다! {scheduled_time}, {dosage_mg}mg")
                    play_alert_voice(scheduled_time)

                    print(f"{scheduled_time}, {dosage_mg}mg 복용 하셨나요? '먹었어'라고 답해주세요.")
                    upload_stt()
                    is_take = check_taken_llm(schedule_id, wav_path)
                    
                    if is_take:
                        taken_at = datetime.now().strftime("%y.%m.%d.%H.%M")

                        payload = {"schedule_id": schedule_id, "taken_at": taken_at}

                        print(f"복약기록 전송중...(ID: {schedule_id})")
    
                        try:
                            res = requests.put(f"{base_url}/api/user/histories", json=payload)
                            if res.status_code == 200:
                                print("기록 전송 성공")
                                pending_alerts.remove(alert)
                            else:
                                print(f"전송 실패: {res.status_code} - {res.text}")
                        except Exception as e:
                            print(f"전송 에러: {e}")
                        
                        continue
                    else:
                        print(f"답변 대기중. (ID: {schedule_id})")
                        alert["alert_count"] = alert_count+1
                        alert["next_alert_time"] =now + timedelta(minutes=DOSAGE_TIME)
        else:
            time.sleep(1)

# 1. 오늘 복약 스케줄만 가져오기
def get_today_schedule():
    url = f"{base_url}/api/user/histories?user_id={USER_ID}"
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
                    print(f" 파싱 실패: {r['scheduled_time']} {parse_err}")

            return today_schedule

         else:
            print(f"get 서버 응답 오류 : {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"get 서버 요청 실패: {e}")
        return []

# 2. 받아온 스케줄로 알람 등록
def register_schedule(schedule_list):
    now = datetime.now().replace(second=0, microsecond=0)
    schedule_list.sort(key=lambda r: datetime.fromisoformat(r["scheduled_time"]))

    for record in schedule_list:
        sched_dt = datetime.fromisoformat(record["scheduled_time"])
        sched_time = sched_dt.replace(second=0, microsecond=0)
        if sched_time < now:
            continue

        time_str = sched_time.strftime("%H:%M")
        dosage_mg = record["dosage_mg"]
        schedule_id = record["id"]
        unique_key = f"{schedule_id}_{sched_dt.strftime('%Y-%m-%d %H:%M')}"

        if unique_key not in scheduled_times_set:
            if time_str == "00:00":
                print("[자정알람] 00:00 알람 별도 등록")
                schedule.every().day.at("00:00").do(
                    medicine_alert,
                    scheduled_time=time_str,
                    dosage_mg=dosage_mg,
                    schedule_id=schedule_id
                )
            else:
                schedule.every().day.at(time_str).do(
                    medicine_alert,
                    scheduled_time=time_str,
                    dosage_mg=dosage_mg,
                    schedule_id=schedule_id
                )

            scheduled_times_set.add(unique_key)
            print(f"알람 등록 : {unique_key}, 용량 : {dosage_mg}mg")

            if sched_time == now:
                medicine_alert(
                    scheduled_time=time_str,
                    dosage_mg=dosage_mg,
                    schedule_id=schedule_id
                )

# 3. 다음 먹을 약의 정보
def get_next_medicine_info():
    schedule_list = get_today_schedule()
    now = datetime.now()
    
    for record in sorted(schedule_list, key=lambda r: r["scheduled_time"]):
        sched_time = datetime.fromisoformat(record["scheduled_time"])
        if sched_time > now : 
            time_str = sched_time.strftime("%p %I시%M분").replace("AM","오전").replace("PM","오후")
            dosage_mg = record["dosage_mg"]
            print(f"{sched_time.strftime('%Y-%m-%d')}|{time_str}|{dosage_mg}mg")
            return f"{USER_NAME}님의 다음 약은 {time_str}에 {dosage_mg}밀리그램 만큼 드셔야합니다."

    return "오늘 남은 약이 없습니다."

# 4. 매일 자정에 실행할 리셋 + 알람 등록 함수
def daily_refresh():
    print(f"[{datetime.now()}] 자정 이후 알람 새로고침")
    schedule.clear()
    scheduled_times_set.clear()
    schedule_list = get_today_schedule()
    register_schedule(schedule_list)

#오늘 복약 스케줄 요약
def get_today_schedule_summary():
    schedule_list = get_today_schedule()
    if not schedule_list:
        return f"{USER_NAME}님의 오늘 복약 스케줄이 없습니다."

    summary = f"{USER_NAME}님의 오늘 복약 스케줄은 다음과 같습니다."
    for r in sorted(schedule_list, key=lambda r: r["scheduled_time"]):
        sched_time = datetime.fromisoformat(r["scheduled_time"])
        time_str = sched_time.strftime("%p %I시 %M분").replace("AM","오전").replace("PM","오후")
        print(f"{sched_time.strftime('%Y-%m-%d')}|{time_str}|{r['dosage_mg']}mg")
        summary += f" {time_str}에 {r['dosage_mg']}밀리그램,"

    return summary.strip(" ,")

# 4. 메인 스케줄러 루프
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


if __name__ == "__main__":
    run_scheduler()
