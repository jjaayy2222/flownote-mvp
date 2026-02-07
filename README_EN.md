# 🎯 FlowNote - AI-Powered PARA Classification System

<p align="center">
  <a href="./README.md">한국어</a> | <a href="./README_EN.md"><strong>English</strong></a>
</p>

> **AI automatically organizes your documents**  
> Smart organization with PARA methodology (Projects, Areas, Resources, Archives)

<br>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/fastapi-latest-green?logo=fastapi&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/streamlit-latest-red?logo=streamlit&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/celery-5.4-green?logo=celery&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/redis-7.x-red?logo=redis&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/license-MIT-green?logo=opensourceinitiative&logoColor=white" style="margin: 4px;" />
</p>

<br>

<p align="center">
  <img src="https://github.com/jjaayy2222/flownote-mvp/actions/workflows/ci.yml/badge.svg" alt="CI" />
  <img src="https://codecov.io/gh/jjaayy2222/flownote-mvp/branch/main/graph/badge.svg" alt="codecov" />
</p>

<br>

---

## 📖 Table of Contents

1. [Introduction](#1-introduction)
2. [Key Features](#2-key-features)
3. [Tech Stack](#3-tech-stack)
4. [Project Structure](#4-project-structure)
5. [Testing](#5-testing)
6. [Installation & Setup](#6-installation--setup)
7. [Usage](#7-usage)
8. [Development History](#8-development-history)
9. [Roadmap](#9-roadmap)
10. [FAQ](#10-faq)
11. [Contributing](#11-contributing)
12. [License](#12-license)
13. [Developer](#13-developer)

---

## 1. 📖 Introduction

**FlowNote** is an AI-powered document auto-classification system. It learns your profession and areas of interest to intelligently categorize uploaded documents using the PARA method.

### 💡 Core Concept

```
    User Onboarding (Profession, Interests)
        ↓
    GPT-4o learns user context
        ↓
    File Upload (PDF, TXT, MD)
        ↓
    AI classifies using PARA method
        ↓
    Results + Confidence Score + Keywords
        ↓
    🎉 Done!
```

**Example:**
- **Input**: `"Project_Proposal_2025.pdf"`
- **Result**: `📋 Projects` (95% confidence)
- **Keywords**: `project`, `deadline`, `goals`

---

## 2. ✨ Key Features

### 2.1 🚀 **Smart Onboarding**
- GPT-4o analyzes user profession
- Recommends 10 areas → User selects 5
- Stores and utilizes user context

### 2.2 📄 **AI-Based Auto Classification**
```
📋 Projects
   → Specific goals with deadlines
   Example: "Implement dashboard by November"

🎯 Areas
   → Ongoing responsibility areas
   Example: "Team performance management"

📚 Resources
   → Reference materials/learning resources
   Example: "Python optimization guide"

📦 Archives
   → Completed project storage
   Example: "2024 project results"
```

### 2.3 🔍 **Keyword Search System**
- FAISS vector search engine
- OpenAI Embeddings integration
- Real-time similarity scores
- Search history tracking

### 2.4 📊 **Real-time Dashboard**
- PARA classification statistics visualization
- File tree structure display
- Recent activity logs
- Metadata management

### 2.5 🎯 **Context-Based Classification**
- Reflects user profession/interests
- Confidence scores (0-100%)
- Auto-generated keyword tags
- Classification reasoning

### 2.6 🤖 **Intelligent Automation System**
- **Auto Reclassification**: Daily/weekly AI review of low-confidence documents
- **Smart Archiving**: Suggests moving Projects untouched for 90+ days to Archives
- **Periodic Reports**: Weekly/monthly classification statistics and insights
- **System Monitoring**: Auto-checks background tasks and sync integrity
- **Celery & Redis**: Reliable distributed task queue processing

### 2.7 🔗 **MCP Server & Obsidian Integration** (v5.0 Phase 1)
- **Model Context Protocol (MCP)**: MCP server implementation for Claude Desktop integration
- **Obsidian Sync**: Real-time Vault file detection and auto-classification
- **Conflict Resolution**: 3-way conflict detection and auto-resolution (Rename strategy)
- **MCP Tools**: `classify_content`, `search_notes`, `get_automation_stats`
- **MCP Resources**: PARA category-based file listings

### 2.8 📊 **Modern Next.js Dashboard** (v5.0 Phase 2-3)
- **Sync Monitor**: Real-time monitoring of Obsidian connection and MCP server status
- **PARA Graph View**: React Flow-based file-category relationship visualization
  - Node click interactions (Toast notifications)
  - Deterministic Layout (position persistence on refresh)
  - Zoom/Pan support
- **Advanced Stats**: Recharts-based statistical charts
  - Activity Heatmap (GitHub-style annual activity)
  - Weekly Trend (12-week file processing volume)
  - PARA Distribution (Category proportion Pie Chart)
- **Mobile Responsive**: Auto-switching desktop/mobile navigation
- **Accessibility**: ARIA attributes and screen reader support

### 2.9 🔄 **WebSocket Real-time Updates** (v6.0 Phase 1)
- **Real-time Sync**: Removed polling, WebSocket-based bidirectional communication
- **Event-driven Updates**: Instant UI reflection on file classification and sync status changes
- **Network Optimization**: 50%+ traffic reduction
- **Connection Management**: Auto-reconnect, Heartbeat mechanism
- **Type Safety**: TypeScript-based event type definitions

### 2.10 🔍 **Conflict Diff Viewer** (v6.0 Phase 2)
- **Visual Comparison**: Monaco Editor-based Side-by-Side Diff viewer
- **3 Resolution Options**: Keep Local / Keep Remote / Keep Both
- **Markdown Preview**: Rendered preview of conflicting files
- **Syntax Highlighting**: File type-specific syntax highlighting
- **Inline Diff**: Line-by-line change highlighting

### 2.11 🌍 **Internationalization (i18n)** (v6.0 Phase 3)
- **Korean/English Support**: next-intl-based multilingual system
- **Dynamic Language Switching**: URL-based routing (`/ko/dashboard`, `/en/dashboard`)
- **SEO Optimization**: Language-specific metadata and sitemap
- **Backend API i18n**: Accept-Language header-based response localization
- **Date/Number Formatting**: Locale-specific auto-formatting

---

## 3. 💻 Tech Stack

### 3.1 Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.11.10 | Development Language |
| **FastAPI** | 0.120.4 | REST API Framework |
| **WebSocket** | - | Real-time Bidirectional Communication (v6.0) |
| **LangChain** | 1.0.2 | AI Chain Management |
| **Celery** | 5.4.0 | Async Task Queue & Scheduling |
| **Redis** | 7.x | Message Broker & Cache |
| **Flower** | 2.0.1 | Celery Monitoring Dashboard |
| **SQLite** | 3 | Metadata Storage |
| **Uvicorn** | 0.38.0 | ASGI Server |

### 3.2 Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| **Next.js** | 16.1.1 | React Framework (App Router) |
| **React** | 19.2.3 | UI Library |
| **TypeScript** | 5.x | Type Safety |
| **Tailwind CSS** | ^4.x | Styling |
| **Shadcn UI** | latest | UI Component Library |
| **React Flow** | ^11.11.4 | Graph Visualization |
| **Recharts** | ^3.6.0 | Chart Library |
| **Sonner** | ^2.0.7 | Toast Notifications |
| **next-intl** | ^3.x | Internationalization (v6.0) |
| **Monaco Editor** | ^0.52.x | Diff Viewer (v6.0) |

### 3.3 LLM & AI
| Technology | Model | Purpose |
|------------|-------|---------|
| **OpenAI API** | GPT-4o | PARA Classification, Area Recommendations |
| **OpenAI API** | GPT-4o-mini | Lightweight Tasks |
| **OpenAI Embeddings** | text-embedding-3-small | Vector Embeddings |

### 3.4 Search & Data
| Technology | Version | Purpose |
|------------|---------|---------|
| **FAISS** | 1.12.0 | Vector Search Engine |
| **pdfplumber** | 0.11.0 | PDF Parsing |
| **python-dotenv** | 1.1.1 | Environment Variable Management |

---

## 4. 📁 Project Structure

```bash
flownote-mvp/
│
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment variable template
├── .gitignore
│
├── backend/                            # FastAPI Backend
│   ├── main.py                         # FastAPI main app (Entrypoint)
│   ├── celery_app/                     # Celery configuration
│   │   ├── celery.py                   # Celery instance
│   │   ├── config.py                   # Celery settings
│   │   └── tasks/                      # Async tasks (reclassification, archiving, etc.)
│   │
│   ├── mcp/                            # MCP Server ✨
│   │   ├── server.py                   # MCP server implementation
│   │   └── tools/                      # MCP Tools (classify, search, etc.)
│   │
│   ├── api/                            # API Endpoints
│   │   ├── endpoints/
│   │   │   ├── websocket.py            # WebSocket endpoint (v6.0) ✨
│   │   │   ├── sync.py                 # Sync & Diff API (v6.0) ✨
│   │   │   └── ...
│   │   ├── deps.py                     # Dependencies (i18n locale extraction) ✨
│   │   └── exceptions.py               # Multilingual exception handling (v6.0) ✨
│   │
│   ├── services/                       # Business Logic (Service Layer)
│   │   ├── obsidian_sync.py            # Obsidian synchronization ✨
│   │   ├── conflict_resolution_service.py  # Conflict resolution ✨
│   │   ├── websocket_manager.py        # WebSocket connection management (v6.0) ✨
│   │   ├── diff_service.py             # Diff generation (v6.0) ✨
│   │   ├── i18n_service.py             # Multilingual messages (v6.0) ✨
│   │   └── ...
│   │
│   ├── core/                           # Core configuration (v6.0) ✨
│   │   └── config.py                   # Application settings
│   │
│   ├── embedding.py                    # Embedding generation
│   ├── faiss_search.py                 # FAISS search
│   ├── classifier/                     # PARA classification logic
│   └── ...
│
├── web_ui/                             # Next.js Frontend ✨
│   ├── src/
│   │   ├── app/
│   │   │   ├── [locale]/               # Multilingual routing (v6.0) ✨
│   │   │   │   ├── page.tsx            # Dashboard
│   │   │   │   ├── graph/page.tsx      # Graph View
│   │   │   │   └── stats/page.tsx      # Statistics
│   │   │   └── not-found.tsx           # 404 page (i18n) ✨
│   │   ├── components/                 # React components
│   │   │   ├── dashboard/
│   │   │   │   └── SyncMonitor.tsx     # WebSocket-based (v6.0) ✨
│   │   │   ├── para/GraphView.tsx      # Graph View
│   │   │   ├── conflict/               # Conflict Diff Viewer (v6.0) ✨
│   │   │   │   ├── DiffViewer.tsx
│   │   │   │   └── ConflictResolver.tsx
│   │   │   └── layout/
│   │   │       └── LanguageSwitcher.tsx # Language switcher (v6.0) ✨
│   │   ├── i18n/                       # i18n configuration (v6.0) ✨
│   │   │   └── config.ts
│   │   ├── locales/                    # Translation files (v6.0) ✨
│   │   │   ├── ko.json
│   │   │   └── en.json
│   │   ├── hooks/                      # Custom Hooks
│   │   │   └── useWebSocket.ts         # WebSocket Hook (v6.0) ✨
│   │   └── config/                     # Configuration files
│   ├── middleware.ts                   # next-intl middleware (v6.0) ✨
│   └── package.json
│
├── data/                               # Data storage
├── docs/                               # Documentation
│   └── P/                              # Project phase documentation
│       ├── v5_phase1_mcp_server/       # MCP server docs
│       ├── v5_phase2_frontend/         # Frontend docs
│       ├── v5_phase3_visualization/    # Visualization docs
│       ├── v6.0_phase1_websocket/      # WebSocket docs (v6.0) ✨
│       ├── v6.0_phase2_diff_viewer/    # Diff Viewer docs (v6.0) ✨
│       └── v6.0_phase3_i18n/           # i18n docs (v6.0) ✨
├── README.md                           # Korean documentation
└── README_EN.md                        # This document (English)
```

---

## 5. 🧪 Testing & Quality Assurance

FlowNote ensures stability through rigorous testing and quality management.

### 5.1 Running Tests

```bash
# Run all tests
pytest

# Generate coverage report
pytest --cov=backend --cov-report=term-missing
```

### 5.2 Test Coverage (Phase 4 baseline)

| Module | Coverage | Notes |
|--------|----------|-------|
| **Overall** | **55%** | Focus on core logic |
| `util.py` (Celery Tasks) | 80%+ | Automation tasks |
| `parallel_processor.py` | 100% | Parallel processing |
| `classification_service.py` | 89% | Core logic |

---

## 6. 🚀 Installation & Setup

### 6.1 Prerequisites
- **Python**: 3.11+
- **Node.js**: 18+
- **OpenAI API Key**: [platform.openai.com](https://platform.openai.com/)
- **Redis Server**: 6.2+ (for Celery broker)

### 6.2 Installation

```bash
# 1. Clone repository
git clone https://github.com/jjaayy2222/flownote-mvp.git
cd flownote-mvp

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install Redis (macOS)
brew install redis
brew services start redis

# 4. Install Python packages
pip install -r requirements.txt

# 5. Install Frontend packages
cd web_ui
npm install
cd ..

# 6. Configure environment variables
cp .env.example .env
# Set OpenAI API key and REDIS_URL in .env file
```

### 6.3 Running All Services

FlowNote requires **4 terminals** (+ 1 additional for MCP server if needed).

**1. FastAPI Backend (Terminal 1)**
```bash
# From project root directory
# Unix/macOS:
source venv/bin/activate  # or pyenv activate <your-env>
# Windows:
# venv\Scripts\activate

python -m uvicorn backend.main:app --reload
# → http://127.0.0.1:8000
```

**2. Next.js Frontend (Terminal 2)**
```bash
cd web_ui
npm run dev
# → http://localhost:3000
# Korean: http://localhost:3000/ko
# English: http://localhost:3000/en
```

**3. Celery Worker & Beat (Terminal 3)**
```bash
# Run Worker and Beat together (development)
celery -A backend.celery_app.celery worker --beat --loglevel=info
```

**4. Flower Monitoring (Terminal 4)**
```bash
celery -A backend.celery_app.celery flower --port=5555
# → http://localhost:5555
```

**5. MCP Server (Terminal 5) - Optional**
```bash
# For Claude Desktop integration
python -m backend.mcp.server
# Or auto-start via Claude Desktop configuration
```

---

## 7. 📖 Usage

### 7.1 **Step 1: Onboarding**
1. Navigate to `Tab 1: Onboarding`
2. Enter name and profession, select areas

### 7.2 **Step 2: File Classification**
1. Navigate to `Tab 2: File Classification`
2. Upload files and start classification

### 7.3 **Step 3: Real-time Monitoring (v6.0)**
1. Check real-time sync status in Dashboard's Sync Monitor
2. Monitor WebSocket connection status and event logs

### 7.4 **Step 4: Conflict Resolution (v6.0)**
1. Receive notification when conflict occurs
2. Compare changes in Diff Viewer
3. Choose Keep Local / Keep Remote / Keep Both

### 7.5 **Step 5: Language Switching (v6.0)**
1. Click language switcher in top-right corner
2. Select Korean/English
3. URL auto-updates and UI reflects changes instantly

### 7.6 **Step 6: Automation Monitoring**
1. Access [Flower Dashboard](http://localhost:5555)
2. Check auto-reclassification/report generation tasks in `Tasks` tab
3. Monitor worker status in `System` tab

### 7.7 **Step 7: CLI Usage**
```bash
# Classify single file
python -m backend.cli classify "path/to/file.txt" [user_id]
```

---

## 8. 📈 Development History

### Progress by Issue

| Issue | Completed | Key Features | Status |
|-------|-----------|--------------|--------|
| [#1-10] | ~11/11 | Phase 1-2 (MVP) | ✅ |
| [#10.4] | 12/16 | Celery Automation & Scheduling | ✅ |
| [#10.11] | 02/04 | v6.0 Phase 3 (i18n) | ✅ |

### Major Commit History
- `v5.0` - MCP Server, Next.js Dashboard, Graph View
- `v6.0 Phase 1` - WebSocket Real-time Updates
- `v6.0 Phase 2` - Conflict Diff Viewer
- `v6.0 Phase 3` - Internationalization (i18n) ✅

---

## 9. 🗺️ Roadmap

### ✅ Completed Features (v5.0)
- [x] Smart Onboarding & PARA Classification
- [x] Celery-based Async Task Queue
- [x] Periodic Auto-reclassification and Archiving Scheduler
- [x] Flower Monitoring Integration
- [x] MCP Server Implementation ✨
- [x] Obsidian Sync and Conflict Resolution ✨
- [x] Next.js-based Modern Dashboard ✨
- [x] PARA Graph View & Advanced Stats ✨
- [x] Mobile Responsive UI ✨

### ✅ Completed Features (v6.0)
- [x] **Phase 1: WebSocket Real-time Updates** ✨
  - [x] Removed polling approach
  - [x] Bidirectional real-time communication
  - [x] Auto-reconnect mechanism
  - [x] Event-driven UI updates
  - [x] 50% network traffic reduction

- [x] **Phase 2: Conflict Diff Viewer** ✨
  - [x] Monaco Editor-based Side-by-Side comparison
  - [x] 3 resolution options (Keep Local/Remote/Both)
  - [x] Markdown preview
  - [x] Syntax highlighting
  - [x] Inline diff display

- [x] **Phase 3: Internationalization (i18n)** ✨
  - [x] next-intl-based multilingual system
  - [x] Korean/English full support
  - [x] URL-based language routing
  - [x] Backend API response localization
  - [x] SEO metadata internationalization
  - [x] Locale-specific date/number formatting

### 🚧 Planned (v7.0)
- [ ] Additional language support (Japanese, Chinese)
- [ ] AI-based auto-translation
- [ ] Advanced search filters
- [ ] File version history

---

## 10. ❓ FAQ

### Q1. Is Redis required?
**A**: Yes, Redis is required as Celery's message broker and must be running.

### Q2. When do automation tasks run?
**A**: According to the schedule defined in `backend/celery_app/config.py` (e.g., reclassification at 00:00 daily).

---

## 11. 🤝 Contributing
Issues and PRs are welcome.

---

## 12. 📄 License
MIT License

---

## 13. 👤 Developer
**Jay** ([@jjaayy2222](https://github.com/jjaayy2222))

---

<br>

<p align="center">
  <strong>FlowNote</strong> - AI organizes your documents 🚀
</p>
