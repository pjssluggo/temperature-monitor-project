document.addEventListener('DOMContentLoaded', () => {
    // 10초마다 대시보드 데이터를 업데이트하는 함수
    async function updateDashboard() {
        try {
            const response = await fetch('/api/latest_data');
            if (!response.ok) {
                console.error('데이터를 가져오는 데 실패했습니다:', response.status);
                return;
            }
            const latestData = await response.json();

            latestData.forEach(item => {
                const deviceName = item.device_name;
                // 각 장치에 해당하는 HTML 요소 찾기
                const tempDiv = document.getElementById(`temp-div-${deviceName}`);
                const tempValue = document.getElementById(`temp-value-${deviceName}`);
                const setTemp = document.getElementById(`set-temp-${deviceName}`);
                const status = document.getElementById(`status-${deviceName}`);
                const cardHeader = document.getElementById(`header-${deviceName}`); // 카드 헤더 추가

                if (tempDiv && tempValue && setTemp && status && cardHeader) {
                    // 1. 온도 값 업데이트
                    tempValue.textContent = item.temperature !== null ? item.temperature.toFixed(1) : '--';
                    setTemp.textContent = item.set_temp !== null ? `${item.set_temp.toFixed(1)}°C` : '--°C';

                    // 2. 상태 텍스트 및 클래스 업데이트
                    // 기존 클래스 제거
                    tempDiv.classList.remove('good', 'warn');
                    status.classList.remove('good', 'warn');

                    if (item.is_alarm) {
                        status.textContent = 'WAR';
                        status.classList.add('warn');
                        cardHeader.classList.remove('offline-header');
                        tempDiv.classList.add('warn');
                    } else if (item.status === '정상') {
                        status.textContent = 'GO';
                        status.classList.add('good');
                        cardHeader.classList.remove('offline-header');
                        tempDiv.classList.add('good');
                    } else { // 오프라인
                        status.textContent = 'OFF';
                        status.classList.add('good'); // 오프라인일 때도 기본 색상 (warn 아님)
                        cardHeader.classList.add('offline-header');
                        tempDiv.classList.add('good');
                    }
                }
            });
        } catch (error) {
            console.error('대시보드 업데이트 중 오류 발생:', error);
        }
    }

    // 페이지 로드 후 10초마다 주기적으로 호출
    // 초기 로드 시에도 한 번 호출하여 최신 데이터 표시
    updateDashboard(); 
    setInterval(updateDashboard, 10000); // 10초 (10000 밀리초)
});