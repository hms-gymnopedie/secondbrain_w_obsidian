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

        // Admin
        this.initAdmin();

        // Track items
        this.queueItems = new Map();  // id -> element
        this.resultCards = new Map(); // id -> data
    }

    // -------- Admin Tools --------
    initAdmin() {
        const btnTag = document.getElementById('btn-tag-cleaner');
        const btnFormat = document.getElementById('btn-vault-format');
        const modalTags = document.getElementById('modal-tag-cleaner');
        const modalFormat = document.getElementById('modal-vault-format');
        const formatSelect = document.getElementById('format-folder-select');
        const btnDoFormat = document.getElementById('btn-do-format');

        // Modal close buttons
        document.querySelectorAll('.modal-close, .modal-close-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.modal').forEach(m => m.classList.remove('active'));
            });
        });

        // Tag Cleaner
        if (btnTag) {
            btnTag.addEventListener('click', () => {
                modalTags.classList.add('active');
                this.analyzeTags();
            });
        }

        // Vault Format
        if (btnFormat) {
            btnFormat.addEventListener('click', async () => {
                modalFormat.classList.add('active');
                await this.loadFoldersIntoSelect(formatSelect);
            });
        }

        if (formatSelect) {
            formatSelect.addEventListener('change', async () => {
                const folderName = formatSelect.value;
                const infoContainer = document.getElementById('folder-info-container');
                const btnDoFormat = document.getElementById('btn-do-format');
                const infoSubfolders = document.getElementById('info-subfolders');
                const infoFiles = document.getElementById('info-files');
                const infoSize = document.getElementById('info-size');

                btnDoFormat.disabled = !folderName;
                
                if (folderName) {
                    try {
                        const response = await fetch(`/api/folders/${encodeURIComponent(folderName)}/info`);
                        if (response.ok) {
                            const data = await response.json();
                            infoSubfolders.textContent = data.subfolders;
                            infoFiles.textContent = data.files;
                            infoSize.textContent = data.size;
                            infoContainer.style.display = 'block';
                        } else {
                            throw new Error('정보 조회 실패');
                        }
                    } catch (e) {
                        console.error('Failed to load folder info:', e);
                        infoContainer.style.display = 'none';
                    }
                } else {
                    infoContainer.style.display = 'none';
                }
            });
        }

        if (btnDoFormat) {
            btnDoFormat.addEventListener('click', () => {
                const folder = formatSelect.value;
                const fileCount = document.getElementById('info-files').textContent;
                if (confirm(`정말로 '${folder}' 폴더와 안에 있는 ${fileCount}개의 파일을 모두 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`)) {
                    this.cleanupFolder(folder);
                }
            });
        }
    }

    async analyzeTags() {
        const container = document.getElementById('tag-analysis-results');
        container.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>AI가 태그를 분석하고 있습니다...</p></div>`;

        try {
            const response = await fetch('/api/tags/analyze');
            if (!response.ok) throw new Error('태그 분석 실패');
            
            const data = await response.json();
            this.renderTagSuggestions(data.suggested_groups);
        } catch (e) {
            container.innerHTML = `<p style="color:var(--accent-red); padding:20px;">분석 중 오류가 발생했습니다: ${e.message}</p>`;
        }
    }

    renderTagSuggestions(groups) {
        const container = document.getElementById('tag-analysis-results');
        if (!groups || groups.length === 0) {
            container.innerHTML = `<p style="padding:20px; text-align:center; color:var(--text-secondary);">병합이 권장되는 유사한 태그가 없습니다.</p>`;
            return;
        }

        container.innerHTML = '';
        groups.forEach(group => {
            const el = document.createElement('div');
            el.className = 'tag-group-card';
            el.innerHTML = `
                <div class="tag-group-header">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span style="color: var(--text-accent); font-weight: 600;">#</span>
                        <input type="text" class="primary-tag-input" value="${group.primary_tag}" title="최종 병합될 태그 이름을 수정할 수 있습니다." style="border: 1px solid var(--border-primary); background: var(--bg-secondary); color: var(--text-primary); padding: 4px 8px; border-radius: 4px; font-size: 13px; outline: none; width: 140px; font-weight: 600; transition: border-color 0.2s;" onfocus="this.style.borderColor='var(--accent-blue)'" onblur="this.style.borderColor='var(--border-primary)'" />
                    </div>
                    <button class="btn btn-primary btn-sm btn-merge" style="padding: 4px 10px; font-size: 11px;">병합 실행</button>
                </div>
                <div class="tag-synonyms" style="margin-top: 8px;">
                    <span class="synonym-tag" style="background: rgba(0,122,255,0.1); color: var(--accent-blue); border-color: rgba(0,122,255,0.2); cursor: default; pointer-events: none;">기존 대표: #${group.primary_tag}</span>
                    ${group.synonyms.map(s => `<span class="synonym-tag merge-target" data-tag="${s}" title="클릭하여 병합 대상에서 제외/포함 토글">#${s}</span>`).join('')}
                </div>
                <div class="tag-reason" style="margin-top: 4px;">${group.reason}</div>
            `;

            const mergeBtn = el.querySelector('.btn-merge');
            const inputEl = el.querySelector('.primary-tag-input');
            const targetTags = el.querySelectorAll('.merge-target');

            // 토글 이벤트 리스너 추가
            targetTags.forEach(tagEl => {
                tagEl.addEventListener('click', () => {
                    tagEl.classList.toggle('excluded');
                });
            });
            
            mergeBtn.addEventListener('click', async () => {
                const finalTag = inputEl.value.trim().replace(/^#/, ''); // 맨 앞의 # 제거
                if (!finalTag) {
                    this.showToast('대표 태그 이름을 입력해주세요.', 'error');
                    inputEl.focus();
                    return;
                }

                // 제외된(.excluded) 태그를 걸러내고 활성화된 태그의 data-tag 값만 추출
                const activeSynonyms = Array.from(targetTags)
                    .filter(tagEl => !tagEl.classList.contains('excluded'))
                    .map(tagEl => tagEl.getAttribute('data-tag'));

                // 최종 태그(finalTag)와 일치하는 것만 제외한 나머지(기존 대표 포함) 병합 대상 구성
                const allTagsToMerge = [...new Set([...activeSynonyms, group.primary_tag])].filter(t => t !== finalTag);

                if (allTagsToMerge.length === 0) {
                    this.showToast('병합할 대상 태그가 없습니다. (모두 제외됨)', 'info');
                    return;
                }

                mergeBtn.disabled = true;
                mergeBtn.textContent = '처리 중...';
                inputEl.disabled = true;
                targetTags.forEach(t => t.style.pointerEvents = 'none');

                await this.mergeTags(finalTag, allTagsToMerge);
                
                el.style.opacity = '0.5';
                el.style.pointerEvents = 'none';
                mergeBtn.textContent = '완료됨';
            });

            container.appendChild(el);
        });
    }

    async mergeTags(target, toMerge) {
        try {
            const response = await fetch('/api/tags/merge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_tag: target, tags_to_merge: toMerge })
            });
            if (response.ok) {
                this.showToast(`✅ 태그 병합 완료: #${target}`, 'success');
            } else {
                throw new Error('병합 실패');
            }
        } catch (e) {
            this.showToast(`❌ 태그 병합 오류: ${e.message}`, 'error');
        }
    }

    async loadFoldersIntoSelect(selectEl) {
        try {
            const response = await fetch('/api/folders');
            if (response.ok) {
                const folders = await response.json();
                selectEl.innerHTML = '<option value="">폴더를 선택하세요</option>';
                folders.forEach(f => {
                    const opt = document.createElement('option');
                    opt.value = f;
                    opt.textContent = f;
                    selectEl.appendChild(opt);
                });
            }
        } catch (e) {
            console.error('Failed to load folders:', e);
        }
    }

    async cleanupFolder(folder) {
        const btn = document.getElementById('btn-do-format');
        btn.disabled = true;
        btn.textContent = '삭제 중...';

        try {
            const response = await fetch('/api/folders/cleanup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder: folder })
            });
            
            if (response.ok) {
                this.showToast(`🗑️ '${folder}' 폴더가 정리되었습니다.`, 'success');
                document.getElementById('modal-vault-format').classList.remove('active');
            } else {
                const data = await response.json();
                throw new Error(data.detail || '정리 실패');
            }
        } catch (e) {
            this.showToast(`❌ 오류: ${e.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = '폴더 비우기';
        }
    }

    // -------- Queue --------

    addQueueItem(id, filename, sourceType) {
        if (this.queueItems.has(id)) {
            // Already added by optimistic WS update
            return;
        }
        
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

    updateQueueItem(id, stage, progress, message, filename = null) {
        let el = this.queueItems.get(id);
        if (!el) {
            if (filename) {
                // If WS payload arrived before the POST fetch finishes, pre-populate the queue UI.
                this.addQueueItem(id, filename, 'text');
                el = this.queueItems.get(id);
            } else {
                return;
            }
        }

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
