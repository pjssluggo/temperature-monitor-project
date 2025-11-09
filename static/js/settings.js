document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const deviceModalEl = document.getElementById('deviceModal');
    const deviceModal = new bootstrap.Modal(deviceModalEl);
    const deviceForm = document.getElementById('deviceForm');
    const deviceModalLabel = document.getElementById('deviceModalLabel');
    const deviceIdInput = document.getElementById('deviceId');
    const deviceNameInput = document.getElementById('deviceName');
    const deviceIpInput = document.getElementById('deviceIp');
    const devicePortInput = document.getElementById('devicePort');
    const deviceControllerIdInput = document.getElementById('deviceControllerId');
    const deviceAlarmThresholdInput = document.getElementById('deviceAlarmThreshold');
    const deviceMemoInput = document.getElementById('deviceMemo');
    const pushoverSettingsForm = document.getElementById('pushoverSettingsForm');
    const deviceTableBody = document.querySelector('#device-table tbody');
    const newDeviceBtn = document.getElementById('newDeviceBtn');

    // --- Constants ---
    const RELOAD_DELAY = 1000;
    const ALERT_TIMEOUT = 5000;

    // --- Functions ---

function showAlert(message, type = 'success') {
    const alertContainer = document.getElementById('alert-container');
    const alertEl = document.createElement('div');
    alertEl.className = `alert alert-${type} alert-dismissible fade show`;
    alertEl.role = 'alert';
    alertEl.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    alertContainer.appendChild(alertEl);
    setTimeout(() => {
        const alertInstance = bootstrap.Alert.getOrCreateInstance(alertEl);
        if (alertInstance) {
            alertInstance.close();
        }
    }, ALERT_TIMEOUT);
}

function prepareNewDeviceModal() {
    deviceForm.reset();
    deviceIdInput.value = '';
    deviceModalLabel.textContent = '새 장치 추가';
}

function prepareEditDeviceModal(device) {
    deviceForm.reset();
    deviceIdInput.value = device.id;
    deviceNameInput.value = device.name;
    deviceIpInput.value = device.ip;
    devicePortInput.value = device.port;
    deviceControllerIdInput.value = device.controller_id;
    deviceAlarmThresholdInput.value = device.alarm_threshold ?? '';
    deviceMemoInput.value = device.memo || '';
    deviceModalLabel.textContent = '장치 정보 수정';
    deviceModal.show();
}

async function saveDevice() {
    const deviceId = deviceIdInput.value;
    const data = {
        name: deviceNameInput.value,
        ip: deviceIpInput.value,
        port: devicePortInput.value,
        controller_id: deviceControllerIdInput.value,
        alarm_threshold: deviceAlarmThresholdInput.value || null,
        memo: deviceMemoInput.value || null
    };

    // --- 입력값 검증 ---
    if (!data.port || isNaN(parseInt(data.port, 10))) {
        showAlert('포트 번호는 필수이며, 숫자만 입력해야 합니다.', 'danger');
        return;
    }
    if (!data.controller_id || data.controller_id.length !== 2) {
        showAlert('컨트롤러 ID는 필수이며, 두 자리로 입력해야 합니다. (예: 01, 07, 15)', 'danger');
        return;
    }

    // 분기: 새 장치 추가 vs. 기존 장치 수정
    if (deviceId) {
        // --- 기존 장치 수정 ---
        try {
            const response = await fetch(`/api/devices/${deviceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (response.ok) {
                deviceModal.hide();
                showAlert(result.message, 'success');
                setTimeout(() => window.location.reload(), RELOAD_DELAY);
            } else {
                throw new Error(result.message);
            }
        } catch (error) {
            showAlert(`수정 실패: ${error.message}`, 'danger');
        }
    } else {
        // --- 새 장치 추가 (연결 테스트 포함) ---
        showAlert(`[${data.name}] 장치 연결을 테스트 중입니다...`, 'info');
        try {
            // 1. 연결 테스트
            const testResponse = await fetch('/api/test_connection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ip: data.ip, port: data.port, controller_id: data.controller_id })
            });
            const testResult = await testResponse.json();
            if (!testResponse.ok || !testResult.success) {
                throw new Error(testResult.message || '장치와 통신할 수 없습니다. IP, 포트, ID를 확인해주세요.');
            }

            // 2. 테스트 성공 시 장치 추가
            const addResponse = await fetch('/api/devices', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const addResult = await addResponse.json();
            if (addResponse.ok) {
                deviceModal.hide();
                showAlert(`✅ [${data.name}] 연결 성공! ${addResult.message}`, 'success');
                setTimeout(() => window.location.reload(), RELOAD_DELAY);
            } else {
                throw new Error(addResult.message);
            }
        } catch (error) {
            showAlert(`🚨 저장 실패: ${error.message}`, 'danger');
        }
    }
}

async function deleteDevice(deviceId, deviceName) {
    if (!confirm(`정말로 '${deviceName}' 장치를 삭제하시겠습니까?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/devices/${deviceId}`, { method: 'DELETE' });
        const result = await response.json();
        if (response.ok) {
            showAlert(result.message, 'success');
            setTimeout(() => window.location.reload(), RELOAD_DELAY);
        } else {
            throw new Error(result.message);
        }
    } catch (error) {
        showAlert(`오류: ${error.message}`, 'danger');
    }
}

async function testDeviceConnection(device) {
    showAlert(`'${device.name}' 장치와 연결을 테스트하는 중입니다...`, 'info');
    try {
        const response = await fetch('/api/test_connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ip: device.ip,
                port: device.port,
                controller_id: device.controller_id
            })
        });
        const result = await response.json();
        if (response.ok && result.success) {
            showAlert(`✅ [${device.name}] 연결 성공! 현재 온도는 ${result.temperature.toFixed(1)}°C 입니다.`, 'success');
        } else {
            throw new Error(result.message || '알 수 없는 오류');
        }
    } catch (error) {
        showAlert(`🚨 [${device.name}] 연결 실패: ${error.message}. IP, 포트, ID 및 네트워크 연결을 확인하세요.`, 'danger');
    }
}

    async function handlePushoverFormSubmit(event) {
    event.preventDefault();
    const data = {
        api_token: document.getElementById('pushoverApiToken').value,
        user_keys: document.getElementById('pushoverUserKeys').value
    };

    try {
        const response = await fetch('/api/settings/pushover', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (response.ok) {
            showAlert(result.message, 'success');
        } else {
            throw new Error(result.message);
        }
    } catch (error) {
        showAlert(`오류: ${error.message}`, 'danger');
    }
    }

    function handleDeviceTableClick(event) {
        const target = event.target;
        const deviceRow = target.closest('tr');
        if (!deviceRow) return;

        if (target.matches('.btn-edit')) {
            const device = JSON.parse(target.dataset.device);
            prepareEditDeviceModal(device);
        } else if (target.matches('.btn-delete')) {
            const deviceId = target.dataset.id;
            const deviceName = target.dataset.name;
            deleteDevice(deviceId, deviceName);
        } else if (target.matches('.btn-test')) {
            const device = JSON.parse(target.dataset.device);
            testDeviceConnection(device);
        }
    }

    // --- Event Listeners ---
    if (newDeviceBtn) {
        newDeviceBtn.addEventListener('click', prepareNewDeviceModal);
    }

    if (deviceTableBody) {
        deviceTableBody.addEventListener('click', handleDeviceTableClick);
    }

    document.querySelector('#deviceModal .btn-primary').addEventListener('click', saveDevice);

    if (pushoverSettingsForm) {
        pushoverSettingsForm.addEventListener('submit', handlePushoverFormSubmit);
    }
});