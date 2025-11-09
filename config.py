# -*- coding: utf-8 -*-
import os
import json
import database

# --- 1. 기본 설정 ---
COMPANY_NAME = "진푸드시스템"

# 현재 스크립트 파일의 절대 경로를 기준으로 데이터베이스 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'data', 'monitoring.db')
TABLE_NAME = 'temp_logs'
POLL_INTERVAL = 10 # 데이터 수집 주기 (초)

# --- 2. 동적 설정 로딩 ---
def load_devices():
    """DB에서 장치 목록을 불러옵니다."""
    return database.get_all_devices()

def load_pushover_config():
    """DB에서 Pushover 설정을 불러옵니다."""
    settings = database.get_settings()
    try:
        user_keys = json.loads(settings.get('pushover_user_keys', '[]'))
    except json.JSONDecodeError:
        user_keys = []
    return {
        'api_token': settings.get('pushover_api_token', ''),
        'user_keys': user_keys
    }