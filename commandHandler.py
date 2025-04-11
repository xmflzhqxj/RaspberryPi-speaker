import re

from MedicineSchedule import get_next_medicine_info, get_today_schedule_summary
from RequestTts import text_to_voice

# llm 전wake word로 특정 command를 입력 받았을 때 처리
command_patterns = [
    {
        "pattern": r"다음.*복약.*(시간|정보)",
        "handler": get_next_medicine_info
    },
    {
        "pattern": r"오늘.*복약.*(스케줄|시간|정보)",
        "handler": get_today_schedule_summary
    }
]

def handle_command(text):
    for command in command_patterns:
        if re.search(command["pattern"], text):
            response = command["handler"]()
            text_to_voice(response)
            return

    text_to_voice("무슨 말씀이신지 잘 모르겠어요.")

