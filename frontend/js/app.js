/**
 * Second Brain - Main Application
 * Orchestrates the dropzone, dashboard, API calls, and WebSocket.
 */
(function () {
    'use strict';

    const API_BASE = window.location.origin;
    const WS_URL = `ws://${window.location.host}/api/ws`;

    // Initialize UI
    const dashboard = new DashboardUI();
    window.showToast = (msg, type) => dashboard.showToast(msg, type);

    // Initialize Dropzone
    const dropzone = new DropzoneHandler('dropzone', 'file-input', {
        onFilesSelected: handleFilesSelected,
        maxFileSizeMB: 50,
    });

    // -------- WebSocket --------
    let ws = null;
    let wsReconnectTimer = null;

    function connectWebSocket() {
        try {
            ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                dashboard.setConnectionStatus(true);
                if (wsReconnectTimer) {
                    clearInterval(wsReconnectTimer);
                    wsReconnectTimer = null;
                }
            };

            ws.onmessage = (event) => {
                try {
                    const status = JSON.parse(event.data);
                    handleProcessingUpdate(status);
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };

            ws.onclose = () => {
                dashboard.setConnectionStatus(false);
                // Reconnect after 3 seconds
                if (!wsReconnectTimer) {
                    wsReconnectTimer = setInterval(() => {
                        connectWebSocket();
                    }, 3000);
                }
            };

            ws.onerror = () => {
                dashboard.setConnectionStatus(false);
            };
        } catch (e) {
            dashboard.setConnectionStatus(false);
        }
    }

    // -------- File Upload --------
    async function handleFilesSelected(files) {
        const formData = new FormData();
        files.forEach(file => formData.append('files', file));

        // Add items to queue immediately
        files.forEach(file => {
            const tempId = `temp-${Date.now()}-${file.name}`;
            dashboard.addQueueItem(tempId, file.name, getSourceType(file.name));
        });

        try {
            const response = await fetch(`${API_BASE}/api/upload`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`Upload failed: ${response.statusText}`);
            }

            const results = await response.json();

            results.forEach(result => {
                if (result.status === 'error') {
                    dashboard.showToast(`❌ ${result.filename}: ${result.message}`, 'error');
                } else {
                    dashboard.showToast(`📤 ${result.filename} 업로드 완료`, 'info');
                    // Replace temp queue item
                    dashboard.addQueueItem(result.id, result.filename, result.source_type);
                }
            });

        } catch (error) {
            dashboard.showToast(`업로드 실패: ${error.message}`, 'error');
        }
    }

    // -------- URL Processing --------
    const urlInput = document.getElementById('url-input');
    const urlBtn = document.getElementById('btn-url');

    urlBtn.addEventListener('click', handleURLSubmit);
    urlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleURLSubmit();
    });

    async function handleURLSubmit() {
        const url = urlInput.value.trim();
        if (!url) {
            dashboard.showToast('URL을 입력해주세요.', 'error');
            return;
        }

        // Basic URL validation
        try {
            new URL(url);
        } catch {
            dashboard.showToast('올바른 URL을 입력해주세요.', 'error');
            return;
        }

        urlInput.value = '';
        urlBtn.disabled = true;
        urlBtn.textContent = '처리 중...';

        try {
            const response = await fetch(`${API_BASE}/api/url`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            if (!response.ok) {
                throw new Error(`URL processing failed: ${response.statusText}`);
            }

            const result = await response.json();
            dashboard.addQueueItem(result.id, url, 'web');
            dashboard.showToast(`🌐 웹페이지 처리를 시작합니다`, 'info');

        } catch (error) {
            dashboard.showToast(`URL 처리 실패: ${error.message}`, 'error');
        } finally {
            urlBtn.disabled = false;
            urlBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                스크래핑
            `;
        }
    }

    // -------- Processing Updates --------
    function handleProcessingUpdate(status) {
        dashboard.updateQueueItem(status.id, status.stage, status.progress, status.message);

        if (status.stage === 'done') {
            dashboard.showToast(`✅ 노트 생성 완료!`, 'success');
            // Fetch the completed note details
            fetchNoteDetails(status.id);
            // Refresh history
            fetchHistory();
        } else if (status.stage === 'error') {
            dashboard.showToast(`❌ 처리 실패: ${status.message}`, 'error');
        }
    }

    async function fetchNoteDetails(noteId) {
        try {
            const response = await fetch(`${API_BASE}/api/note/${noteId}`);
            if (response.ok) {
                const note = await response.json();
                dashboard.addResultCard(note);
            }
        } catch (e) {
            console.error('Failed to fetch note details:', e);
        }
    }

    async function fetchHistory() {
        try {
            const response = await fetch(`${API_BASE}/api/history`);
            if (response.ok) {
                const history = await response.json();
                dashboard.renderHistory(history);

                // Also restore result cards for completed items
                history.forEach(item => {
                    if (item.status === 'done' && !dashboard.resultCards.has(item.id)) {
                        dashboard.addResultCard(item);
                    }
                });
            }
        } catch (e) {
            console.error('Failed to fetch history:', e);
        }
    }

    // -------- Helpers --------
    function getSourceType(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const mapping = {
            'pdf': 'pdf', 'docx': 'docx', 'doc': 'docx',
            'pptx': 'pptx', 'ppt': 'pptx',
            'png': 'image', 'jpg': 'image', 'jpeg': 'image',
            'gif': 'image', 'bmp': 'image', 'webp': 'image',
            'md': 'markdown', 'txt': 'text', 'csv': 'text',
        };
        return mapping[ext] || 'text';
    }

    // -------- Sidebar Toggle --------
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');

    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        sidebar.classList.toggle('collapsed');
    });

    // -------- Refresh Button --------
    const refreshBtn = document.getElementById('btn-refresh');
    refreshBtn.addEventListener('click', () => {
        fetchHistory();
        dashboard.showToast('새로고침 완료', 'info');
    });

    // -------- Initialize --------
    connectWebSocket();
    fetchHistory();

    // Set vault path display
    document.getElementById('vault-path').textContent = 'Vault: ./vault';

})();
