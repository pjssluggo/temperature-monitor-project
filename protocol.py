# -*- coding: utf-8 -*-
import socket
import time
import logging

log = logging.getLogger()

# --- 1. 프로토콜 상수 ---
STX = b'\x02'; ETX = b'\x03'
HEADER_READ_TEMP = b'RXTP0'; HEADER_READ_DATA = b'RDTP0' # 현재 온도 읽기/응답 (RDTP0)
HEADER_READ_SETTING = b'RXTS0'                        # 설정값 읽기 명령어 (RX TS0)
HEADER_READ_SETTING_RESP = b'RDTS0'                   # 설정값 읽기 응답 (RD TS0)

# --- 2. 프로토콜 유틸리티 함수 ---
def calculate_bcc(packet_bytes):
    """ STX부터 ETX까지 XOR 체크섬 계산 """
    bcc = 0;
    for byte in packet_bytes: bcc ^= byte;
    return bytes([bcc])

def ascii_to_hex_val(byte_val):
    """ ASCII 문자 ('0'-'9', 'A'-'F')를 16진수 값으로 변환 """
    if byte_val < 0x40: return byte_val - 0x30; # '0' ~ '9'
    else: return byte_val - 0x37; # 'A' ~ 'F'

def ascii_hex_to_temperature(data_bytes, decimal_flag):
    """ 4바이트 ASCII-Hex를 온도로 변환 (음수 포함) """
    try:
        if len(data_bytes) != 4: raise ValueError("데이터 길이가 4가 아님");
        val_bytes = [ascii_to_hex_val(b) for b in data_bytes];
        temp_val_16bit = (val_bytes[0] << 12) | (val_bytes[1] << 8) | (val_bytes[2] << 4) | val_bytes[3];
        if temp_val_16bit & 0x8000: temperature = (temp_val_16bit - 0x10000);
        else: temperature = temp_val_16bit;
        if decimal_flag == b'1': temperature = temperature / 10.0;
        return temperature;
    except Exception as e: log.error(f"ASCII-Hex({data_bytes.decode() if data_bytes else 'N/A'})->온도 변환 실패: {e}"); return None;

def parse_response_base(response_bytes, expected_id_bytes, expected_header):
    """ 공통 응답 파싱 로직 (STX, BCC, ID, Header 검증) """
    if not response_bytes: raise ValueError("응답 없음");
    stx_index = response_bytes.find(STX);
    if stx_index == -1: raise ValueError(f"응답 STX 없음 in {response_bytes.hex()}");
    packet = response_bytes[stx_index:];

    if len(packet) < 5: raise ValueError(f"응답 너무 짧음: {packet.hex()}");
    if packet[-2] != ETX[0]: raise ValueError(f"응답 ETX 없음: {packet.hex()}");

    packet_to_check = packet[:-1]; received_bcc = packet[-1:]; calculated_bcc = calculate_bcc(packet_to_check);
    if received_bcc != calculated_bcc: raise ValueError(f"BCC 불일치 R:{received_bcc.hex()} C:{calculated_bcc.hex()} in {packet.hex()}");

    if packet[1:3] != expected_id_bytes: raise ValueError(f"ID 불일치 Exp:{expected_id_bytes.decode()} Rcv:{packet[1:3].decode()} in {packet.hex()}");

    header_len = len(expected_header)
    if len(packet) < 3 + header_len + 2: raise ValueError(f"헤더 포함하기에 너무 짧음: {packet.hex()}");
    if packet[3:3+header_len] != expected_header: raise ValueError(f"헤더 불일치 Exp:'{expected_header.decode()}' Rcv:{packet[3:3+header_len].decode()} in {packet.hex()}");

    payload = packet[3+header_len:-2]
    return payload

def parse_temperature_response(response_bytes, expected_id_bytes):
    """ 현재 온도 응답 (RDTP0) 파싱 """
    try:
        payload = parse_response_base(response_bytes, expected_id_bytes, HEADER_READ_DATA)
        if len(payload) < 6: raise ValueError(f"페이로드 길이 부족 (<6): {payload.hex()}");
        data_bytes = payload[0:4]; decimal_flag = payload[4:5]; error_flag = payload[5:6];
        
        error_val = ascii_to_hex_val(error_flag[0])
        if error_val & 0b0001: raise ConnectionError("센서 오픈 에러");
        if error_val & 0b0010: raise ConnectionError("센서 쇼트 에러");

        op_status = {
            'run': bool(error_val & 0b10000000), 'comp': bool(error_val & 0b01000000),
            'defrost': bool(error_val & 0b00100000), 'fan': bool(error_val & 0b00010000)
        }
        return ascii_hex_to_temperature(data_bytes, decimal_flag), op_status
    except Exception as e: log.error(f"ID {expected_id_bytes.decode()}: 현재온도 파싱 예외: {e} (응답: {response_bytes})"); return None, None;

def parse_set_temperature_response(response_bytes, expected_id_bytes):
    """ 설정 온도 읽기 응답 (RD TS0) 파싱 """
    try:
        payload = parse_response_base(response_bytes, expected_id_bytes, HEADER_READ_SETTING_RESP)
        if len(payload) < 5: raise ValueError(f"페이로드 길이 부족 (<5): {payload.hex()}");
        data_bytes = payload[0:4]; decimal_flag = payload[4:5];
        return ascii_hex_to_temperature(data_bytes, decimal_flag);
    except Exception as e: log.error(f"ID {expected_id_bytes.decode()}: 설정온도 파싱 예외: {e} (응답: {response_bytes})"); return None;

# --- 3. 통신 실행 함수 ---
def send_command_and_receive(ip, port, controller_id, command_bytes, expected_header_str=""):
    """ 소켓 통신 공통 함수 """
    log.debug(f"ID {controller_id}: -> {ip}:{port} | CMD({expected_header_str}): {command_bytes.hex()}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5.0); s.connect((ip, port)); s.sendall(command_bytes);
            log.debug(f"ID {controller_id}: CMD 전송 완료, 응답 대기 시작...");
            response_bytes = s.recv(1024);
        log.debug(f"ID {controller_id}: <- {ip}:{port} | RCV({expected_header_str}): {response_bytes.hex() if response_bytes else '응답 없음'}")
        return response_bytes
    except socket.timeout: log.error(f"ID {controller_id}: {ip}:{port} 5초간 {expected_header_str} 응답 없음 (send 후 timeout)"); return None;
    except ConnectionRefusedError: log.error(f"ID {controller_id}: {ip}:{port} 연결 거부됨. 대상 장치(컨버터)가 해당 포트에서 실행 중인지, 전원/네트워크 연결이 올바른지 확인해주세요."); return None;
    except Exception as e: log.error(f"ID {controller_id}: {ip}:{port} {expected_header_str} 소켓 오류 - {e}"); return None;

def get_temperature_from_device(ip, port, controller_id):
    """ 현재 온도 읽기 (RXTP0) """
    controller_id_bytes = controller_id.encode('ascii'); packet_without_bcc = STX + controller_id_bytes + HEADER_READ_TEMP + ETX; bcc = calculate_bcc(packet_without_bcc); command = packet_without_bcc + bcc;
    response_bytes = send_command_and_receive(ip, port, controller_id, command, "RXTP0");
    if response_bytes: return parse_temperature_response(response_bytes, controller_id_bytes);
    else: return None, None;

def get_set_temperature_from_device(ip, port, controller_id):
    """ 설정 온도 읽기 (RX TS0) """
    controller_id_bytes = controller_id.encode('ascii'); packet_without_bcc = STX + controller_id_bytes + HEADER_READ_SETTING + ETX; bcc = calculate_bcc(packet_without_bcc); command = packet_without_bcc + bcc;
    response_bytes = send_command_and_receive(ip, port, controller_id, command, "RXTS0")
    if response_bytes: return parse_set_temperature_response(response_bytes, controller_id_bytes);
    else: return None;