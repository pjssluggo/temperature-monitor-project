import sqlite3
import logging
import config
import datetime

log = logging.getLogger()

def get_db_connection():
    """ DB 연결 생성 (Row 팩토리 사용) """
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute(f'''
                CREATE TABLE IF NOT EXISTS {config.TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,  /* DATETIME 대신 TEXT로 지정 */
                    device_name TEXT NOT NULL,
                    temperature REAL NOT NULL
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    ip TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    controller_id TEXT NOT NULL,
                    alarm_threshold REAL,
                    memo TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('pushover_api_token', '')")
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('pushover_user_keys', '[]')")

            conn.commit()
            log.info(f"DB 테이블 초기화 완료 ({config.DATABASE})")
    except Exception as e:
        log.critical(f"DB 초기화 실패 - {e}")
        raise

def log_temperature_to_db(device_name, temperature):
    """ 측정된 현재 온도를 DB에 삽입 """
    try:
        if not isinstance(temperature, (int, float)) or temperature != temperature or abs(temperature) == float('inf'):
            log.warning(f"{device_name}: 유효하지 않은 온도 값({temperature})은 DB에 저장하지 않음."); return;
        
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_db_connection() as conn:
            c = conn.cursor();
            c.execute(f"INSERT INTO {config.TABLE_NAME} (device_name, timestamp, temperature) VALUES (?, ?, ?)", (device_name, current_time, temperature));
            conn.commit();
            log.debug(f"DB 저장 성공: {device_name}={temperature}°C at {current_time}");
    except Exception as e:
        log.error(f"{device_name}: DB 저장 실패 - {e}");
        raise # 에러를 다시 발생시켜 호출한 쪽에서 알 수 있도록 함

def get_historical_data(device_name, start_date_str, end_date_str, interval_minutes=None):
    """
    상세 페이지 그래프용 과거 데이터 가져오기.
    interval_minutes가 지정되면 해당 분 간격으로 데이터의 평균을 계산합니다.
    """
    with get_db_connection() as conn:
        c = conn.cursor();
        end_date_inclusive = end_date_str + ' 23:59:59'

        if interval_minutes:
            # SQLite에서 unixepoch를 사용하여 시간 그룹화 및 평균 계산
            query = """
                SELECT
                    strftime('%Y-%m-%d %H:%M:00', datetime(CAST(strftime('%s', timestamp) / (60 * ?) AS INTEGER) * (60 * ?), 'unixepoch')) as timestamp,
                    AVG(temperature) as temperature
                FROM temp_logs
                WHERE device_name = ? AND timestamp BETWEEN ? AND ?
                GROUP BY 1
                ORDER BY 1 ASC
            """
            params = (interval_minutes, interval_minutes, device_name, start_date_str, end_date_inclusive)
        else:
            query = "SELECT timestamp, temperature FROM temp_logs WHERE device_name = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp ASC"
            params = (device_name, start_date_str, end_date_inclusive)

        c.execute(query, params)
        
        rows = c.fetchall();
        log.info(f"DB 조회: {device_name} ({start_date_str}~{end_date_str}, 간격: {interval_minutes}분) -> {len(rows)}건")
        return rows;

def get_all_devices():
    """ DB에서 모든 장치 목록 가져오기 """
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, ip, port, controller_id, alarm_threshold, memo FROM devices ORDER BY name")
        return [dict(row) for row in c.fetchall()]

def add_device(name, ip, port, controller_id, alarm_threshold, memo):
    """ DB에 새 장치 추가 """
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO devices (name, ip, port, controller_id, alarm_threshold, memo) VALUES (?, ?, ?, ?, ?, ?)",
            (name, ip, port, controller_id, alarm_threshold, memo)
        )
        conn.commit()

def update_device(device_id, name, ip, port, controller_id, alarm_threshold, memo):
    """ DB의 장치 정보 수정 """
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE devices SET name=?, ip=?, port=?, controller_id=?, alarm_threshold=?, memo=? WHERE id=?",
            (name, ip, port, controller_id, alarm_threshold, memo, device_id)
        )
        conn.commit()

def delete_device(device_id):
    """ DB에서 장치 삭제 """
    with get_db_connection() as conn:
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
        conn.commit()

def get_settings():
    with get_db_connection() as conn:
        return {row['key']: row['value'] for row in conn.execute("SELECT key, value FROM settings").fetchall()}

def update_setting(key, value):
    with get_db_connection() as conn:
        conn.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
        conn.commit()