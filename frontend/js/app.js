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
                    const data = JSON.parse(event.data);
                    if (data.type === 'deleted') {
                        dashboard.removeResultCard(data.id);
                        fetchHistory();
                        return;
                    }
                    handleProcessingUpdate(data);
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

        const categoryInput = document.getElementById('category-input');
        if (categoryInput && categoryInput.value.trim() !== '') {
            formData.append('folder', categoryInput.value.trim());
        }

        dashboard.showToast(`📤 ${files.length}개 파일 업로드 중...`, 'info');

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
                    dashboard.addQueueItem(result.id, result.filename, result.source_type);
                    dashboard.showToast(`✅ ${result.filename} 처리 시작`, 'info');
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

        const categoryInput = document.getElementById('category-input');
        const folder = categoryInput && categoryInput.value.trim() !== '' ? categoryInput.value.trim() : null;

        urlInput.value = '';
        urlBtn.disabled = true;
        urlBtn.textContent = '처리 중...';

        try {
            const response = await fetch(`${API_BASE}/api/url`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, folder }),
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
        dashboard.updateQueueItem(
            status.id, 
            status.stage, 
            status.progress, 
            status.message, 
            status.filename
        );

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

    async function fetchFolders() {
        try {
            const response = await fetch(`${API_BASE}/api/folders`);
            if (response.ok) {
                const folders = await response.json();
                const datalist = document.getElementById('category-list');
                if (datalist) {
                    datalist.innerHTML = '';
                    folders.forEach(folder => {
                        const option = document.createElement('option');
                        option.value = folder;
                        datalist.appendChild(option);
                    });
                }
            }
        } catch (e) {
            console.error('Failed to fetch folders:', e);
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

    // -------- Theme Toggle --------
    const themeToggle = document.getElementById('theme-toggle');
    
    function initTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon(savedTheme);
    }
    
    function updateThemeIcon(theme) {
        if (!themeToggle) return;
        if (theme === 'dark') {
            themeToggle.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;
        } else {
            themeToggle.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
        }
    }
    
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });
    }

    // -------- Refresh Button --------
    const refreshBtn = document.getElementById('btn-refresh');
    refreshBtn.addEventListener('click', () => {
        fetchHistory();
        dashboard.showToast('새로고침 완료', 'info');
    });

    // -------- Delete Note --------
    async function handleDeleteNote(noteId) {
        try {
            const response = await fetch(`${API_BASE}/api/note/${noteId}`, {
                method: 'DELETE',
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Delete failed');
            }

            dashboard.removeResultCard(noteId);
            dashboard.showToast('🗑️ 노트가 삭제되었습니다', 'success');
            fetchHistory();
        } catch (error) {
            dashboard.showToast(`삭제 실패: ${error.message}`, 'error');
        }
    }

    dashboard.setDeleteHandler(handleDeleteNote);

    // -------- Initialize --------
    initTheme();
    connectWebSocket();
    fetchHistory();
    fetchFolders();

})();
