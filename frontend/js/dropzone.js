/**
 * Drag & Drop Zone Handler
 * Manages drag events, file validation, and visual feedback.
 */
class DropzoneHandler {
    constructor(dropzoneId, fileInputId, options = {}) {
        this.dropzone = document.getElementById(dropzoneId);
        this.fileInput = document.getElementById(fileInputId);
        this.overlay = document.getElementById('dropzone-overlay');
        
        this.allowedExtensions = new Set([
            '.pdf', '.docx', '.doc', '.pptx', '.ppt',
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
            '.md', '.txt', '.csv',
        ]);

        this.onFilesSelected = options.onFilesSelected || (() => {});
        this.maxFileSize = (options.maxFileSizeMB || 50) * 1024 * 1024;
        
        this._dragCounter = 0;
        this._init();
    }

    _init() {
        // Drag events on the dropzone
        this.dropzone.addEventListener('dragenter', (e) => this._onDragEnter(e));
        this.dropzone.addEventListener('dragover', (e) => this._onDragOver(e));
        this.dropzone.addEventListener('dragleave', (e) => this._onDragLeave(e));
        this.dropzone.addEventListener('drop', (e) => this._onDrop(e));

        // File input change
        this.fileInput.addEventListener('change', (e) => this._onFileInputChange(e));

        // Browse button
        const browseBtn = document.getElementById('btn-browse');
        if (browseBtn) {
            browseBtn.addEventListener('click', () => this.fileInput.click());
        }

        // Prevent default drag behavior on the document
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            document.body.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });
    }

    _onDragEnter(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragCounter++;
        this.dropzone.classList.add('drag-over');
    }

    _onDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    _onDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragCounter--;
        if (this._dragCounter <= 0) {
            this._dragCounter = 0;
            this.dropzone.classList.remove('drag-over');
        }
    }

    _onDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragCounter = 0;
        this.dropzone.classList.remove('drag-over');

        const files = Array.from(e.dataTransfer.files);
        this._processFiles(files);
    }

    _onFileInputChange(e) {
        const files = Array.from(e.target.files);
        this._processFiles(files);
        // Reset input so same file can be selected again
        this.fileInput.value = '';
    }

    _processFiles(files) {
        const validFiles = [];
        const errors = [];

        for (const file of files) {
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            
            if (!this.allowedExtensions.has(ext)) {
                errors.push(`${file.name}: 지원하지 않는 형식입니다 (${ext})`);
                continue;
            }

            if (file.size > this.maxFileSize) {
                const sizeMB = Math.round(file.size / 1024 / 1024);
                errors.push(`${file.name}: 파일 크기 초과 (${sizeMB}MB)`);
                continue;
            }

            validFiles.push(file);
        }

        if (errors.length > 0) {
            errors.forEach(err => {
                if (window.showToast) {
                    window.showToast(err, 'error');
                }
            });
        }

        if (validFiles.length > 0) {
            this.onFilesSelected(validFiles);
        }
    }

    /**
     * Get file type icon emoji
     */
    static getFileIcon(filename) {
        const ext = '.' + filename.split('.').pop().toLowerCase();
        const icons = {
            '.pdf': '📄', '.docx': '📝', '.doc': '📝',
            '.pptx': '📊', '.ppt': '📊',
            '.png': '🖼️', '.jpg': '🖼️', '.jpeg': '🖼️',
            '.gif': '🖼️', '.bmp': '🖼️', '.webp': '🖼️',
            '.md': '📋', '.txt': '📃', '.csv': '📊',
        };
        return icons[ext] || '📁';
    }

    /**
     * Get CSS class for file type
     */
    static getFileTypeClass(sourceType) {
        const classes = {
            'pdf': 'pdf', 'docx': 'docx', 'pptx': 'pptx',
            'image': 'image', 'markdown': 'text', 'text': 'text',
            'web': 'web',
        };
        return classes[sourceType] || 'text';
    }
}

// Export for use in other files
window.DropzoneHandler = DropzoneHandler;
