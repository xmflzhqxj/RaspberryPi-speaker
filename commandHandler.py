import re

from MedicineSchedule import get_next_medicine_info, get_today_schedule_summary
from RequestTts import text_to_voice

# 기존 명령어 매칭용 패턴
command_patterns = [
    {
        "pattern": r"(다음|앞으로).*?(약|복약).*?(시간|스케줄|정보)?",
        "handler": get_next_medicine_info
    },
    {
        "pattern": r"(오늘).*?(약|복약).*?(시간|스케줄|정보)?",
        "handler": get_today_schedule_summary
    }
]

# === New: responsetype 분류용 키워드 매칭 ===
response_type_keywords = [
    {"keywords": ["밥", "식사", "먹기 전"], "responsetype": "check_meal"},
    {"keywords": ["약 먹어", "약 복용", "약 먹을게"], "responsetype": "induce_medicine"},
    {"keywords": ["약 먹을 시간", "복약 시간", "약 시간"], "responsetype": "taking_medicine_time"},
    {"keywords": ["약 다 먹었어", "복용 완료", "약 다 먹"], "responsetype": "check_medicine"},
]

def classify_responsetype(text):
    text = text.lower()  # 소문자로 변환
    for item in response_type_keywords:
        for keyword in item["keywords"]:
            if keyword in text:
                return item["responsetype"]
    return "daily_talk"  # 기본값

def handle_command(text):
    # 1. 명령어 패턴 먼저 체크
    for command in command_patterns:
        if re.search(command["pattern"], text):
            response = command["handler"]()
            text_to_voice(response)
            return

    # 2. 명령어가 아니면 responsetype 분류로 넘어감
    text_to_voice("무슨 말씀이신지 잘 모르겠어요.")

