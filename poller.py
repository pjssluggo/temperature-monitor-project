# -*- coding: utf-8 -*-
import time
import datetime
import logging
import requests

import config
import protocol
import database
from shared_state import data_lock, alarm_status, last_alarm_times, comm_fail_status, comm_fail_counters, current_set_temps, current_temperatures, initialize_shared_state

log = logging.getLogger()

db_fail_counters = {} # DB 로깅 연속 실패 횟수 카운터

def check_alarm(device_name, temperature, threshold):
    """ 알람 상태 확인, 로깅, 반복 알람 처리 """
    if not isinstance(temperature, (int, float)): return;

    now = datetime.datetime.now()
    is_currently_in_alarm = temperature > threshold;
    was_previously_in_alarm = alarm_status.get(device_name, False);
    last_alarm_time = last_alarm_times.get(device_name)

    if is_currently_in_alarm and not was_previously_in_alarm:
        # 상태 변경: 정상 -> 알람 (최초 알람)
        log.warning(f"[알람 발생] {device_name}: 현재({temperature}°C) > 임계값({threshold}°C)!");
        alarm_status[device_name] = True;
        last_alarm_times[device_name] = now
        send_pushover_notification(f"{device_name} 온도 알람", f"장치 '{device_name}'의 온도가 임계값({threshold}°C)을 초과했습니다. (현재: {temperature}°C)", priority=1)
    elif is_currently_in_alarm and was_previously_in_alarm:
        # 상태 유지: 알람 -> 알람 (반복 알람 확인)
        if last_alarm_time and (now - last_alarm_time).total_seconds() >= 30 * 60:
            log.warning(f"[반복 알람] {device_name}: 30분 이상 알람 상태 지속. 현재({temperature}°C) > 임계값({threshold}°C)!");
            last_alarm_times[device_name] = now # 마지막 알람 시간 갱신
            send_pushover_notification(f"{device_name} 온도 알람 지속", f"장치 '{device_name}'의 온도가 30분 이상 임계값({threshold}°C)을 초과하고 있습니다. (현재: {temperature}°C)", priority=1)
    elif not is_currently_in_alarm and was_previously_in_alarm:
        # 상태 변경: 알람 -> 정상 (알람 해제)
        log.info(f"[알람 해제] {device_name}: 현재({temperature}°C) <= 임계값({threshold}°C) 복구.");
        alarm_status[device_name] = False;
        last_alarm_times[device_name] = None # 알람 해제 시, 마지막 알람 시간 초기화

pushover_config_warning_sent = False

def send_pushover_notification(title, message, priority=0):
    """ Pushover를 통해 스마트폰으로 푸시 알림을 보냅니다. """
    pushover_config = config.load_pushover_config()
    api_token = pushover_config.get('api_token')
    user_keys = pushover_config.get('user_keys', [])

    if not api_token or not user_keys or api_token == 'YOUR_API_TOKEN_HERE':
        global pushover_config_warning_sent
        if not pushover_config_warning_sent:
            log.warning("Pushover 설정(API 토큰 또는 사용자 키)이 비어있어 알림을 보내지 않습니다. 설정 페이지에서 구성해주세요.")
            pushover_config_warning_sent = True # 경고는 한 번만 보냅니다.
        else:
            log.debug("Pushover 설정이 없어 알림을 건너뜁니다.") # 이후에는 디버그 레벨로 조용히 처리
        return # 알림 전송 중단

    for user_key in user_keys:
        try:
            payload = {"token": api_token, "user": user_key, "title": title, "message": message, "priority": priority}
            response = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=10)
            response.raise_for_status()
            log.info(f"Pushover 알림 전송 성공: {user_key}에게 '{title}' 전송")
        except requests.exceptions.RequestException as e:
            log.error(f"Pushover 알림 전송 실패 ({user_key}): {e}")

def data_polling_thread():
    """ 주기적으로 모든 장치의 현재 온도와 설정 온도를 읽어오는 스레드 """
    log.info("폴링 스레드 시작");
    while True:
        start_time = time.time();
        
        # 매 주기마다 DB에서 최신 장치 목록을 다시 불러옵니다.
        devices = config.load_devices()
        if not devices:
            log.warning("등록된 장치가 없습니다. 설정 페이지에서 장치를 추가해주세요.")
            time.sleep(config.POLL_INTERVAL)
            continue
        log.info(f"--- 새 폴링 주기 시작 ({len(devices)}개 장치) ---");

        for device in devices:
            device_name = device['name']; ip = device['ip']; port = device['port']; controller_id = device['controller_id']; alarm_threshold = device.get('alarm_threshold'); log.info(f"{device_name}: 수집 시도...");

            # --- [디버깅] 현재 온도 읽기 핵심 로직 ---
            current_temp, op_status = protocol.get_temperature_from_device(ip, port, controller_id);

            # 💡 [사용자 요청] 통신 성공 시, op_status의 'run' 상태를 항상 True로 설정
            if op_status is not None:
                op_status['run'] = True

            if current_temp is not None:
                log.info(f"✅ 수집 성공: {device_name} = {current_temp:.1f}°C")
                # 수집 성공 시, 공유 변수 업데이트 및 DB 저장 (핵심 기능 유지)
                with data_lock:
                    was_previously_failed = comm_fail_counters.get(device_name, 0) >= 3
                    comm_fail_counters[device_name] = 0 # 실패 카운터 리셋
                    current_temperatures[device_name]['temp'] = current_temp
                    current_temperatures[device_name]['op_status'] = op_status
                    current_temperatures[device_name]['timestamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                # --- 설정 온도 읽기 (실패해도 전체 로직에 영향 없도록) ---
                try:
                    set_temp = protocol.get_set_temperature_from_device(ip, port, controller_id)
                    with data_lock:
                        current_set_temps[device_name] = set_temp
                except Exception as e:
                    log.warning(f"설정 온도 읽기 실패 ({device_name}): {e}")

                if was_previously_failed:
                    log.info(f"✅ [상태 복구] {device_name} 장치가 다시 온라인 상태가 되었습니다.")
                    send_pushover_notification(f"{device_name} 온라인 복구", f"장치 '{device_name}'의 통신이 정상적으로 복구되었습니다.")

                # --- 알람 확인 ---
                if alarm_threshold is not None:
                    check_alarm(device_name, current_temp, alarm_threshold)

                # --- DB 저장 및 실패 처리 ---
                try:
                    database.log_temperature_to_db(device_name, current_temp)
                    # DB 저장이 성공했고, 이전에 실패 기록이 있었다면 복구 로그를 남김
                    if db_fail_counters.get(device_name, 0) > 0:
                        log.info(f"✅ [DB 복구] {device_name} 장치의 데이터베이스 로깅이 정상적으로 복구되었습니다.")
                        db_fail_counters[device_name] = 0 # DB 실패 카운터 리셋
                except Exception as db_e:
                    # DB 저장 실패 시 카운터 증가 및 알림
                    log.error(f"🚨 DB 로깅 실패: {device_name} 온도 {current_temp}°C 기록 중 오류 발생: {db_e}")
                    db_fail_counters[device_name] = db_fail_counters.get(device_name, 0) + 1
                    # 정확히 3회 실패 시점에 한 번만 알림
                    if db_fail_counters.get(device_name, 0) == 3:
                        send_pushover_notification(f"시스템 경고: DB 로깅 실패", f"장치 '{device_name}'의 온도 데이터 기록에 3회 연속 실패했습니다. 서버 상태를 확인해주세요.", priority=1)
            else:
                # 수집 실패 시, 연속 실패 횟수를 1 증가시킴
                with data_lock:
                    comm_fail_counters[device_name] += 1
                    fail_count = comm_fail_counters[device_name]
                log.warning(f"🚨 수집 실패: {device_name}의 현재 온도를 읽을 수 없습니다. (연속 {fail_count}회)")

                # 연속 3회 이상 실패 시에만 오프라인 처리
                if fail_count == 3: # 정확히 3회가 되는 시점에 한 번만 알림
                    log.error(f"🚨 {device_name} 장치가 3회 연속 통신에 실패하여 오프라인으로 처리합니다.")
                    send_pushover_notification(f"{device_name} 오프라인", f"장치 '{device_name}'이 3회 연속 통신에 실패하여 오프라인으로 처리됩니다.", priority=1)
                
                if fail_count >= 3:
                    with data_lock:
                        current_temperatures[device_name].update({'temp': None, 'op_status': None, 'timestamp': None})
                        current_set_temps[device_name] = None

        elapsed = time.time() - start_time; sleep_time = max(0, config.POLL_INTERVAL - elapsed); log.info(f"--- 폴링 완료 (소요: {elapsed:.1f}초). {sleep_time:.1f}초 후 다음 폴링 ---"); time.sleep(sleep_time);