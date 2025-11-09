document.addEventListener('DOMContentLoaded', function() {
    // --- DOM Elements & Initial Data ---
    const chartCanvas = document.getElementById('tempChart');
    const deviceNameEl = document.querySelector('.card-header .label'); 
    const currentTempEl = document.getElementById('current-temp');
    const detailStatusTextEl = document.getElementById('detail-status-text'); 
    const lastUpdatedEl = document.getElementById('last-updated');
    const opStatusEl = document.getElementById('op-status'); 

    if (!chartCanvas || !deviceNameEl) {
        console.error('필수 DOM 요소가 페이지에 없습니다.');
        return;
    }

    const deviceName = deviceNameEl.textContent.trim(); 

    // --- Functions ---
    
    /**
     * Chart.js를 사용하여 온도 변화 그래프를 렌더링합니다.
     */
    function createChart(chartData) {
        // 💡 [수정] 기존 차트 파괴 로직을 맨 위로 이동
        if (window.tempChart instanceof Chart) {
            window.tempChart.destroy();
        }
        
        // 💡 [사용자 요청] 데이터를 Chart.js의 time scale 형식에 맞게 가공
        const dataPoints = chartData.map(item => ({ x: item.timestamp, y: item.temperature }));

        // 💡 [수정] 데이터셋 정의를 데이터 유무 확인 전으로 이동
        const datasets = [
            {
                label: '현재 온도',
                data: dataPoints,
                borderColor: '#007bff', // 파란색
                borderWidth: 2,
                tension: 0.4,
                pointRadius: 1,
                fill: false
            },
            {
                label: '설정 온도',
                data: dataPoints.map(() => setTemp),
                borderColor: '#28a745', // 초록색
                borderWidth: 1.5,
                borderDash: [5, 5], // 점선으로 표시
                pointRadius: 0, // 점은 표시 안 함
                fill: false
            },
            {
                label: '알람 온도',
                data: dataPoints.map(() => alarmThreshold),
                borderColor: '#dc3545', // 빨간색
                borderWidth: 1.5,
                borderDash: [10, 5], // 긴 점선으로 표시
                pointRadius: 0, // 점은 표시 안 함
                fill: false
            }
        ];

        if (chartData.length === 0) {
            console.log("차트 데이터가 비어있어 그래프를 그리지 않습니다.");
            return;
        }

        window.tempChart = new Chart(chartCanvas, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: '현재 온도',
                        data: dataPoints, // 💡 가공된 데이터 포인트 사용
                        borderColor: '#007bff', 
                        borderWidth: 2,
                        tension: 0.4, 
                        pointRadius: 1, 
                        fill: false
                    },
                    // 💡 [사용자 요청] 설정 온도 선 추가
                    {
                        label: '설정 온도',
                        // 모든 데이터 포인트에 대해 동일한 설정 온도를 적용하여 수평선 생성
                        data: dataPoints.map(() => setTemp),
                        borderColor: '#28a745', // 초록색
                        borderWidth: 1.5,
                        borderDash: [5, 5], // 점선으로 표시
                        pointRadius: 0, // 점은 표시 안 함
                        fill: false
                    },
                    // 💡 [사용자 요청] 알람 온도 선 추가
                    {
                        label: '알람 온도',
                        // 모든 데이터 포인트에 대해 동일한 알람 온도를 적용하여 수평선 생성
                        data: dataPoints.map(() => alarmThreshold),
                        borderColor: '#dc3545', // 빨간색
                        borderWidth: 1.5,
                        borderDash: [10, 5], // 긴 점선으로 표시
                        pointRadius: 0, // 점은 표시 안 함
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                    },
                    title: {
                        display: false, // 💡 그래프 제목 제거
                        font: {
                            size: 16,
                            weight: 'bold'
                        }
                    }
                },
                interaction: {
                    mode: 'index', 
                    intersect: false
                },
                scales: {
                    x: {
                        type: 'time', // 💡 [핵심] x축 타입을 'time'으로 변경
                        time: {
                            unit: 'hour', // 💡 [핵심] 시간 단위를 'hour'로 설정
                            displayFormats: {
                                hour: 'HH:mm' // 💡 툴팁 및 라벨 표시 형식을 '시:분'으로 지정
                            },
                            tooltipFormat: 'yyyy-MM-dd HH:mm' // 툴팁에 날짜까지 표시
                        },
                        title: { display: true, text: '시간' },
                        ticks: {
                            source: 'auto' // 💡 자동으로 눈금 조절
                        },
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        title: { display: true, text: '온도 (°C)' },
                        // 💡 [개선] Y축 범위를 데이터에 따라 자동으로 조절하도록 수정
                        // min: 26.0,  
                        // max: 27.5,
                        grace: '10%', // 데이터 최대/최소값에서 10%의 여유 공간을 줌
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.1)'
                        } 
                    }
                }
            }
        });
    }

    /**
     * 운전 상태 UI 업데이트 (RUN, COMP 등) 
     */
    function updateOpStatusUI(opStatus) {
        if (!opStatusEl || !opStatus) return;
        const states = ['run', 'comp', 'defrost', 'fan'];
        const korean = {'run': '운전', 'comp': '압축', 'defrost': '제상', 'fan': '팬'};
        const icons = {'run': 'fa-power-off', 'comp': 'fa-snowflake', 'defrost': 'fa-water', 'fan': 'fa-fan'};
        const colors = {'run': 'bg-primary', 'comp': 'bg-success', 'defrost': 'bg-info text-dark', 'fan': 'bg-secondary'};
        
        let html = '';
        states.forEach(state => {
            const isActive = opStatus[state];
            const activeClass = isActive ? colors[state] : 'bg-light text-dark';
            html += `<span class="badge ${activeClass}" style="white-space: nowrap; font-size: 0.8rem;"><i class="fas ${icons[state]} me-1"></i> ${korean[state]}</span>`;
        });
        opStatusEl.innerHTML = html;
    }


    /**
     * API를 호출하여 현재 장치 상태 및 기록 테이블을 주기적으로 업데이트합니다.
     */
    async function updateCurrentStatus() {
        try {
            const response = await fetch(`/api/device_data/${encodeURIComponent(deviceName)}`);
            if (!response.ok) {
                console.error('상태 업데이트 데이터 가져오기 실패:', response.status);
                return;
            }

            const data = await response.json();
                      
            updateOpStatusUI(data.op_status);

            // 💡 [핵심] 실시간 기록 테이블에 데이터 행 추가 로직
            const tableBody = document.querySelector('.table tbody');
            if (tableBody && data.timestamp && data.temperature !== null) {
                const firstRow = tableBody.rows[0];
                let lastTimestamp = null;
                if (firstRow && firstRow.cells[0]) {
                    lastTimestamp = new Date(firstRow.cells[0].textContent);
                }

                const newTimestamp = new Date(data.timestamp);
                
                // 테이블 갱신 (30분 간격 필터링은 제거)
                const noDataRow = tableBody.querySelector('td[colspan="2"]');
                if (noDataRow) noDataRow.parentElement.remove();

                const newRow = tableBody.insertRow(0);
                const cell1 = newRow.insertCell(0);
                const cell2 = newRow.insertCell(1);
                cell1.textContent = data.timestamp;
                cell2.textContent = data.temperature.toFixed(1);
            }
        } catch (error) {
            console.error('상태 업데이트 중 오류 발생:', error);
        }
    }


    // --- Initialization (최초 실행 블록: DOM 로드 후 실행) ---
    if (typeof historyChartData !== 'undefined' && historyChartData.length > 0) {
        createChart(historyChartData); 
    }
    
    // 10초마다 현재 상태 및 테이블 업데이트 시작
    setInterval(updateCurrentStatus, 10000); 
}); // 💡 [추가 완료] 이 닫는 괄호 때문에 깨짐 현상이 발생했습니다!