from collections import deque
import threading
# 공통으로 사용할 전역 alert 큐
pending_alerts = deque()
mic_lock = threading.Lock()
