/**
 * Dashboard UI Manager
 * Handles rendering of queue items, result cards, history, and toasts.
 */
class DashboardUI {
    constructor() {
        this.queueSection = document.getElementById('queue-section');
        this.queueList = document.getElementById('queue-list');
        this.resultsSection = document.getElementById('results-section');
        this.resultsGrid = document.getElementById('results-grid');
        this.historyList = document.getElementById('history-list');
        this.toastContainer = document.getElementById('toast-container');

        // Stats
        this.statTotal = document.getElementById('stat-total');
        this.statToday = document.getElementById('stat-today');
        this.statKeywords = document.getElementById('stat-keywords');

        // Track items
        this.queueItems = new Map();  // id -> element
        this.resultCards = new Map(); // id -> data
    }

    // -------- Queue --------

    addQueueItem(id, filename, sourceType) {
        this.queueSection.style.display = '';

        const icon = DropzoneHandler.getFileIcon(filename);
        const typeClass = DropzoneHandler.getFileTypeClass(sourceType);

        const el = document.createElement('div');
        el.className = 'queue-item';
        el.id = `queue-${id}`;
        el.innerHTML = `
            <div class="queue-item-icon ${typeClass}">${icon}</div>
            <div class="queue-item-content">
                <div class="queue-item-name">${this._escapeHtml(filename)}</div>
                <div class="queue-item-status">대기 중...</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: 0%"></div>
                </div>
            </div>
        `;

        this.queueList.appendChild(el);
        this.queueItems.set(id, el);
    }

    updateQueueItem(id, stage, progress, message) {
        const el = this.queueItems.get(id);
        if (!el) return;

        const statusEl = el.querySelector('.queue-item-status');
        const progressEl = el.querySelector('.progress-fill');

        if (statusEl) statusEl.textContent = message || stage;
        if (progressEl) progressEl.style.width = `${progress}%`;

        // Update visual state
        el.className = 'queue-item';
        if (stage === 'done') {
            el.classList.add('done');
            // Remove from queue after delay
            setTimeout(() => {
                el.style.transition = 'all 0.5s ease';
                el.style.opacity = '0';
                el.style.transform = 'translateX(20px)';
                setTimeout(() => {
                    el.remove();
                    this.queueItems.delete(id);
                    if (this.queueItems.size === 0) {
                        this.queueSection.style.display = 'none';
                    }
                }, 500);
            }, 2000);
        } else if (stage === 'error') {
            el.classList.add('error');
        }
    }

    // -------- Results --------

    addResultCard(data) {
        this.resultsSection.style.display = '';

        const icon = data.source_type === 'web' ? '🌐' : DropzoneHandler.getFileIcon(data.filename || '');
        const typeClass = DropzoneHandler.getFileTypeClass(data.source_type);

        const keywords = (data.keywords || []).map(kw =>
            `<span class="keyword-tag">#${this._escapeHtml(kw)}</span>`
        ).join('');

        const card = document.createElement('div');
        card.className = 'result-card';
        card.id = `result-${data.id}`;
        card.innerHTML = `
            <div class="result-card-header">
                <div class="result-type-badge ${typeClass}">${icon}</div>
                <div>
                    <div class="result-card-title">${this._escapeHtml(data.title)}</div>
                    <div class="result-card-source">${this._escapeHtml(data.filename || data.source_name || '')}</div>
                </div>
            </div>
            <div class="result-card-summary">${this._escapeHtml(data.summary)}</div>
            <div class="result-card-keywords">${keywords}</div>
            <div class="result-card-footer">
                <span class="result-vault-path">📂 ${this._escapeHtml(data.vault_path || '')}</span>
                <div class="delete-area">
                    <button class="result-action-btn delete-btn" data-id="${data.id}" title="노트 삭제">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                        삭제
                    </button>
                    <div class="delete-confirm" style="display:none;">
                        <span class="delete-confirm-text">삭제할까요?</span>
                        <button class="delete-confirm-yes">확인</button>
                        <button class="delete-confirm-no">취소</button>
                    </div>
                </div>
            </div>
        `;

        const deleteBtn = card.querySelector('.delete-btn');
        const deleteConfirm = card.querySelector('.delete-confirm');
        const confirmYes = card.querySelector('.delete-confirm-yes');
        const confirmNo = card.querySelector('.delete-confirm-no');

        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            deleteBtn.style.display = 'none';
            deleteConfirm.style.display = 'flex';
        });

        confirmNo.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            deleteConfirm.style.display = 'none';
            deleteBtn.style.display = 'flex';
        });

        confirmYes.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            confirmYes.disabled = true;
            confirmYes.textContent = '삭제 중...';
            this._onDeleteNote(data.id);
        });

        // Prepend (newest first)
        this.resultsGrid.prepend(card);
        this.resultCards.set(data.id, data);

        // Update stats
        this._updateStats();
    }

    removeResultCard(id) {
        const card = document.getElementById(`result-${id}`);
        if (card) {
            card.style.transition = 'all 0.4s ease';
            card.style.opacity = '0';
            card.style.transform = 'scale(0.95) translateY(-10px)';
            setTimeout(() => card.remove(), 400);
        }
        this.resultCards.delete(id);
        this._updateStats();

        if (this.resultCards.size === 0) {
            this.resultsSection.style.display = 'none';
        }
    }

    setDeleteHandler(handler) {
        this._onDeleteNote = handler;
    }

    _onDeleteNote(id) {
        // Default no-op, overridden by setDeleteHandler
    }

    // -------- History --------

    renderHistory(items) {
        if (!items || items.length === 0) {
            this.historyList.innerHTML = `
                <div class="history-empty">
                    <span>아직 처리된 자료가 없습니다</span>
                </div>
            `;
            return;
        }

        this.historyList.innerHTML = '';
        items.forEach(item => {
            const icon = item.source_type === 'web' ? '🌐' : DropzoneHandler.getFileIcon(item.filename || '');
            const typeClass = DropzoneHandler.getFileTypeClass(item.source_type);
            const statusEmoji = item.status === 'done' ? '✅' : item.status === 'error' ? '❌' : '⏳';

            const el = document.createElement('div');
            el.className = 'history-item';
            el.innerHTML = `
                <div class="history-item-icon ${typeClass}">${icon}</div>
                <div class="history-item-content">
                    <div class="history-item-title">${this._escapeHtml(item.title || item.filename)}</div>
                    <div class="history-item-meta">${statusEmoji} ${this._escapeHtml(item.source_type)} · ${this._formatDate(item.created_at)}</div>
                </div>
            `;

            el.addEventListener('click', () => {
                const resultEl = document.getElementById(`result-${item.id}`);
                if (resultEl) {
                    resultEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    resultEl.style.animation = 'none';
                    requestAnimationFrame(() => {
                        resultEl.style.animation = 'fadeIn 0.5s ease';
                    });
                }
            });

            this.historyList.appendChild(el);
        });
    }

    // -------- Toasts --------

    showToast(message, type = 'info') {
        const icons = { success: '✅', error: '❌', info: 'ℹ️' };
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
            <span class="toast-message">${this._escapeHtml(message)}</span>
        `;

        this.toastContainer.appendChild(toast);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    // -------- Connection Status --------

    setConnectionStatus(connected) {
        const statusEl = document.getElementById('connection-status');
        if (statusEl) {
            const dot = statusEl.querySelector('.status-dot');
            const text = statusEl.querySelector('span:last-child');
            if (connected) {
                dot.className = 'status-dot connected';
                text.textContent = '서버 연결됨';
            } else {
                dot.className = 'status-dot disconnected';
                text.textContent = '연결 끊김';
            }
        }
    }

    // -------- Private Helpers --------

    _updateStats() {
        const total = this.resultCards.size;
        const allKeywords = new Set();
        let todayCount = 0;
        const today = new Date().toDateString();

        this.resultCards.forEach(data => {
            (data.keywords || []).forEach(kw => allKeywords.add(kw));
            if (data.created_at && new Date(data.created_at).toDateString() === today) {
                todayCount++;
            }
        });

        if (this.statTotal) this.statTotal.textContent = total;
        if (this.statToday) this.statToday.textContent = todayCount;
        if (this.statKeywords) this.statKeywords.textContent = allKeywords.size;
    }

    _escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    _formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        const diff = now - date;

        if (diff < 60000) return '방금 전';
        if (diff < 3600000) return `${Math.floor(diff / 60000)}분 전`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)}시간 전`;
        return date.toLocaleDateString('ko-KR');
    }
}

// Export
window.DashboardUI = DashboardUI;
