# 🧠 Second Brain - Obsidian Knowledge Structuring System

웹 대시보드에서 다양한 자료를 드래그&드롭으로 넣으면, AI가 내용을 분석/요약하고, Obsidian 그래프 뷰에서 바로 활용 가능한 마크다운 노트를 자동 생성합니다.

## ✨ Features

- **🖱️ 드래그 & 드롭 업로드**: PDF, 이미지, Markdown, 텍스트, PPT, DOC 파일 지원
- **🌐 웹 스크래핑**: URL 입력으로 웹페이지 내용 자동 추출
- **🤖 AI 요약 & 키워드 추출**: OpenAI / Gemini / Ollama 지원
- **📝 Obsidian 노트 자동 생성**: YAML frontmatter + 위키링크 + MOC 자동 구성
- **🔗 자동 링킹**: 기존 노트와 키워드 기반 양방향 링크 생성
- **📊 Maps of Content**: 키워드별 MOC 자동 생성 및 인덱싱
- **⚡ 실시간 처리 상태**: WebSocket 기반 진행 상태 표시

## 🏗️ Architecture

```
Frontend (HTML/CSS/JS)  ←→  FastAPI Backend  →  Obsidian Vault
     │                           │
     └── Drag & Drop ──→ Extract → Summarize → Write Notes
         URL Input                    │
                              AI (OpenAI/Gemini/Ollama)
```

## 🚀 Quick Start

### 1. 환경 설정

```bash
# Clone
git clone https://github.com/hms-gymnopedie/secondbrain_w_obsidian.git
cd secondbrain_w_obsidian

# Python 가상 환경
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
cp .env.example .env
# .env 파일에 API 키 입력
```

### 3. 서버 실행

```bash
python -m backend.main
# 또는
uvicorn backend.main:app --reload --port 8000
```

### 4. 대시보드 접속

브라우저에서 `http://localhost:8000` 접속

## 📁 Project Structure

```
secondbrain_w_obsidian/
├── frontend/               # Web Dashboard
│   ├── index.html
│   ├── css/styles.css
│   └── js/
│       ├── app.js          # Main orchestrator
│       ├── dropzone.js     # Drag & drop handler
│       └── dashboard.js    # UI rendering
│
├── backend/                # FastAPI Backend
│   ├── main.py             # App entry point
│   ├── config.py           # Settings
│   ├── models/schemas.py   # Pydantic models
│   ├── routers/upload.py   # API routes
│   └── services/
│       ├── extractor.py    # Multi-format text extraction
│       ├── summarizer.py   # AI summarization
│       ├── metadata.py     # YAML frontmatter generation
│       └── obsidian_writer.py  # Vault file management
│
├── vault/                  # Obsidian Vault (auto-generated)
│   ├── 00_Inbox/
│   ├── 01_Sources/         # Generated notes
│   └── 02_MOC/             # Maps of Content
│
├── .env.example
├── requirements.txt
└── README.md
```

## 🔧 Supported Formats

| Format | Library | Description |
|--------|---------|-------------|
| PDF | PyMuPDF | 고속 PDF 텍스트 추출 |
| DOCX | python-docx | Word 문서 파싱 |
| PPTX | python-pptx | 슬라이드별 텍스트 추출 |
| Image | pytesseract | OCR (한국어+영어) |
| Markdown | Built-in | 직접 파싱 |
| Text | Built-in | 직접 읽기 |
| Web URL | trafilatura | 웹 본문 + 메타데이터 추출 |

## 🤖 AI Providers

`.env` 파일에서 `AI_PROVIDER`를 변경하여 전환:

- **openai**: OpenAI GPT (기본값, 고품질)
- **gemini**: Google Gemini (무료 티어 가능)
- **ollama**: 로컬 Ollama (무료, GPU 권장)

## 📊 Generated Note Format

```markdown
---
title: "문서 제목"
type: source
tags: [키워드1, 키워드2, 키워드3]
source: "원본 파일명 또는 URL"
source_type: pdf
created: 2026-04-15
status: processed
related: ["[[관련노트1]]", "[[관련노트2]]"]
---

# 문서 제목

> [!summary]
> AI 요약문

## 키워드
#키워드1 #키워드2 #키워드3

## 핵심 내용
- 포인트 1
- 포인트 2

## 관련 노트
- [[관련노트1]]
- [[관련노트2]]
```

## 📄 License

MIT
