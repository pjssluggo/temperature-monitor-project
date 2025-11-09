# -*- coding: utf-8 -*-
import threading
import config

# 스레드 간 공유 데이터 접근을 보호하기 위한 잠금(Lock)
data_lock = threading.Lock()

# 공유 상태 변수들을 모듈 레벨에서 초기화합니다.
# 이렇게 해야 다른 모듈에서 import 할 수 있습니다.
alarm_status = {}
comm_fail_status = {}
comm_fail_counters = {} # 연속 통신 실패 횟수 카운터
current_set_temps = {}
current_temperatures = {}
last_alarm_times = {} # 알람 반복 전송을 위해 마지막 알람 시간을 기록

def initialize_shared_state():
    """DB에서 장치 목록을 읽어와 공유 상태 변수들을 초기화합니다."""
    global alarm_status, comm_fail_status, comm_fail_counters, current_set_temps, current_temperatures, last_alarm_times
    devices = config.load_devices()
    
    with data_lock:
        # 기존 데이터를 지우고 새로운 장치 목록으로 갱신합니다.
        alarm_status.clear(); alarm_status.update({device['name']: False for device in devices})
        comm_fail_status.clear(); comm_fail_status.update({device['name']: False for device in devices})
        comm_fail_counters.clear(); comm_fail_counters.update({device['name']: 0 for device in devices})
        current_set_temps.clear(); current_set_temps.update({device['name']: None for device in devices})
        current_temperatures.clear(); current_temperatures.update({device['name']: {'temp': None, 'timestamp': None, 'op_status': None} for device in devices})
        last_alarm_times.clear(); last_alarm_times.update({device['name']: None for device in devices})