# -*- coding: utf-8 -*-
import logging
import threading
import datetime
import json
import os
from urllib.parse import unquote

from flask import Flask, jsonify, render_template as rt, request

import config
import database
from poller import data_polling_thread, initialize_shared_state
from shared_state import data_lock, alarm_status, current_set_temps, current_temperatures, last_alarm_times

# --- 1. 로깅 및 Flask 앱 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s')
log = logging.getLogger()

app = Flask(__name__)

# --- 2. 웹 서버 데이터 처리 함수 ---
def get_latest_data():
    """ 대시보드 표시용 최신 데이터 + 알람 상태 + 설정 온도 가져오기 """
    latest_data = [];
    try:
        devices = config.load_devices()
        with data_lock:
            for device in devices:
                device_name = device['name'];
                is_in_alarm = alarm_status.get(device_name, False);
                read_set_temp = current_set_temps.get(device_name)

                mem_data = current_temperatures.get(device_name, {'temp': None, 'timestamp': None, 'op_status': None})
                current_temp_val = mem_data['temp']
                op_status_val = mem_data['op_status']
                timestamp_str = mem_data['timestamp']

                set_temp_val = None
                try:
                    if read_set_temp is not None: set_temp_val = float(read_set_temp)
                except (ValueError, TypeError):
                    log.warning(f"장치 {device_name}: 메모리 설정 온도 값 '{read_set_temp}'를 float으로 변환 실패. None으로 처리합니다.")
                    set_temp_val = None

                # 상태 결정 로직: 오프라인 > 알람 > 정상 순으로 판단
                if current_temp_val is None:
                    status = "오프라인"
                elif is_in_alarm:
                    status = "알람"
                else:
                    status = "정상"



                latest_data.append({
                    "name": device_name,
                    "temperature": current_temp_val,
                    "status": status,
                    "timestamp": timestamp_str,
                    "device_name": device_name,
                    "is_alarm": is_in_alarm,
                    "alarm_threshold": device.get('alarm_threshold'),
                    "set_temp": set_temp_val,
                    "op_status": op_status_val
                });

    except Exception as e:
        log.error(f"대시보드 데이터 생성 오류: {e}");
    return latest_data

# --- 3. Flask 라우트 (웹 페이지 및 API) ---
@app.route('/')
def dashboard_home():
    """ 메인 대시보드 페이지 """
    current_data = get_latest_data()
    return rt('dashboard.html', data=current_data, company_name=config.COMPANY_NAME);

@app.route('/detail/<device_name>')
def detail_page(device_name):
    """ 상세 정보 페이지 (그래프 + 이력) """
    device_name = unquote(device_name);
    all_data = get_latest_data();
    current_status = next((item for item in all_data if item['device_name'] == device_name), None);
    if not current_status: return "장비 없음", 404;

    today = datetime.date.today()
    seven_days_ago = today - datetime.timedelta(days=7)
    start_date_str = request.args.get('start_date', seven_days_ago.strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))

    try:
        # 💡 [사용자 요청] 그래프 데이터를 1시간(60분) 간격의 평균으로 가져오도록 수정
        rows = database.get_historical_data(device_name, start_date_str, end_date_str, interval_minutes=60)
        history_chart_data = []
        for row in rows:
            # temperature 값이 None이 아닐 경우에만 float으로 변환하여 추가
            if row['temperature'] is not None:
                history_chart_data.append({"timestamp": row['timestamp'], "temperature": float(row['temperature'])})

        history_table_data = []
        last_added_timestamp = None
        # 테이블 데이터는 모든 기록을 대상으로 해야 하므로, DB를 한 번 더 조회합니다.
        table_rows = database.get_historical_data(device_name, start_date_str, end_date_str)

        for row in reversed(table_rows):
            try:
                current_timestamp = datetime.datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
                if last_added_timestamp is None:
                    history_table_data.append({"timestamp": current_timestamp.strftime('%Y-%m-%d %H:%M:%S'), "temperature": float(row['temperature'])})
                    last_added_timestamp = current_timestamp
                elif (last_added_timestamp - current_timestamp).total_seconds() >= 30 * 60:
                    history_table_data.append({"timestamp": current_timestamp.strftime('%Y-%m-%d %H:%M:%S'), "temperature": float(row['temperature'])})
                    last_added_timestamp = current_timestamp
            except (ValueError, TypeError) as e:
                log.error(f"상세 페이지 테이블 데이터 처리 오류 (row: {row}): {e}"); continue;

    except Exception as e:
        log.error(f"상세 페이지 데이터 조회 중 오류: {e}")
        history_chart_data = []
        history_table_data = []

    return rt('detail.html',
        item=current_status,
        history_chart_data_json=json.dumps(history_chart_data),
        history_table_data=history_table_data,
        company_name=config.COMPANY_NAME,
        start_date=start_date_str,
        end_date=end_date_str
    )

@app.route('/api/latest_data')
def api_latest_data():
    """ 최신 데이터를 JSON으로 제공하는 API 엔드포인트 """
    return jsonify(get_latest_data())

@app.route('/api/device_data/<device_name>')
def api_device_data(device_name):
    """ 개별 장비의 현재 상태를 실시간으로 반환하는 API """
    device_name = unquote(device_name)
    item = next((x for x in get_latest_data() if x['device_name'] == device_name), None)
    if not item:
        return jsonify({"error": "device not found or no data"}), 404
    return jsonify(item)

@app.route('/settings')
def settings_page():
    """ 장치 및 알림 설정 페이지 """
    devices = database.get_all_devices()
    pushover_config = config.load_pushover_config()
    return rt('settings.html',
              devices=devices,
              pushover_config=pushover_config,
              company_name=config.COMPANY_NAME)

@app.route('/api/devices', methods=['POST'])
def add_device_api():
    data = request.json
    # IP 주소 유효성 검사 (http:// 또는 https:// 포함 여부) - .get()으로 안전하게 접근
    if data.get('ip', '').startswith('http://') or data.get('ip', '').startswith('https://'):
        return jsonify({"success": False, "message": "IP 주소는 'http://' 또는 'https://'를 포함할 수 없습니다. 순수 IP 주소만 입력해주세요."}), 400

    # 컨트롤러 ID 유효성 검사 추가 (두 자리 문자열인지 확인)
    controller_id = data.get('controller_id')
    if not controller_id or len(str(controller_id)) != 2:
        return jsonify({"success": False, "message": "컨트롤러 ID는 필수이며, 두 자리로 입력해야 합니다. (예: 01, 07, 15)"}), 400

    try:
        database.add_device(data['name'], data['ip'], int(data['port']), data['controller_id'], float(data['alarm_threshold']) if data.get('alarm_threshold') else None, data.get('memo'))
        return jsonify({"success": True, "message": "장치가 추가되었습니다."})
    except Exception as e:
        log.error(f"장치 추가 API 오류: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/devices/<int:device_id>', methods=['PUT'])
def update_device_api(device_id):
    data = request.json
    # IP 주소 유효성 검사 (http:// 또는 https:// 포함 여부) - .get()으로 안전하게 접근
    if data.get('ip', '').startswith('http://') or data.get('ip', '').startswith('https://'):
        return jsonify({"success": False, "message": "IP 주소는 'http://' 또는 'https://'를 포함할 수 없습니다. 순수 IP 주소만 입력해주세요."}), 400

    # 컨트롤러 ID 유효성 검사 추가 (두 자리 문자열인지 확인)
    controller_id = data.get('controller_id')
    if not controller_id or len(str(controller_id)) != 2:
        return jsonify({"success": False, "message": "컨트롤러 ID는 필수이며, 두 자리로 입력해야 합니다. (예: 01, 07, 15)"}), 400

    try:
        database.update_device(device_id, data['name'], data['ip'], int(data['port']), data['controller_id'], float(data['alarm_threshold']) if data.get('alarm_threshold') else None, data.get('memo'))
        return jsonify({"success": True, "message": "장치 정보가 수정되었습니다."})
    except Exception as e:
        log.error(f"장치 수정 API 오류: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
def delete_device_api(device_id):
    try:
        database.delete_device(device_id)
        return jsonify({"success": True, "message": "장치가 삭제되었습니다."})
    except Exception as e:
        log.error(f"장치 삭제 API 오류: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/settings/pushover', methods=['POST'])
def update_pushover_settings_api():
    data = request.json
    try:
        api_token = data.get('api_token', '')
        # user_keys를 쉼표로 구분된 문자열로 받아 리스트로 변환 후 JSON 문자열로 저장
        user_keys_str = data.get('user_keys', '')
        user_keys_list = [key.strip() for key in user_keys_str.split(',') if key.strip()]
        
        database.update_setting('pushover_api_token', api_token)
        database.update_setting('pushover_user_keys', json.dumps(user_keys_list))
        
        return jsonify({"success": True, "message": "Pushover 설정이 저장되었습니다."})
    except Exception as e:
        log.error(f"Pushover 설정 저장 API 오류: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/test_connection', methods=['POST'])
def test_connection_api():
    """ 장치와의 통신을 테스트하는 API """
    data = request.json
    ip = data.get('ip')
    port = data.get('port')
    controller_id = data.get('controller_id')

    if not all([ip, port, controller_id]):
        return jsonify({"success": False, "message": "IP, 포트, 컨트롤러 ID는 필수입니다."}), 400

    log.info(f"연결 테스트 시도: {ip}:{port} (ID: {controller_id})")
    temp, _ = protocol.get_temperature_from_device(ip, int(port), controller_id)

    if temp is not None:
        return jsonify({"success": True, "message": "연결 성공!", "temperature": temp})
    else:
        return jsonify({"success": False, "message": "장치에서 응답이 없습니다."}), 500

# --- 4. 서버 실행 ---
if __name__ == '__main__':
    os.makedirs(os.path.dirname(config.DATABASE), exist_ok=True)
    database.init_db();
    initialize_shared_state()
    
    poller = threading.Thread(target=data_polling_thread, name="PollerThread", daemon=True);
    poller.start();
    
    log.info(f"Flask 서버 시작 (http://0.0.0.0:5000)");
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False);