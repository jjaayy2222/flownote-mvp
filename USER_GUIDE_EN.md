# 📖 FlowNote User Guide (v9.0 (In Progress))

<p align="center">
  <a href="./USER_GUIDE.md">한국어</a> | <a href="./USER_GUIDE_EN.md"><strong>English</strong></a>
</p>

> New to FlowNote? Follow this guide to get started!

---

## 📖 Table of Contents

1. [Before You Begin](#1-before-you-begin)
2. [First Run](#2-first-run)
3. [Onboarding Process](#3-onboarding-process)
4. [Document Classification](#4-document-classification)
5. [Using Search](#5-using-search)
6. [Hybrid RAG Search](#6-hybrid-rag-search)
7. [AI Assistant Chat](#7-ai-assistant-chat)
8. [Using the Dashboard](#8-using-the-dashboard)
9. [Automation Settings](#9-automation-settings)
10. [Obsidian Integration](#10-obsidian-integration)
11. [Language Settings](#11-language-settings)
12. [Troubleshooting](#12-troubleshooting)
13. [🛠️ Technical & Developer Appendix](#13-technical--developer-appendix)
    - [RAG Eval & Performance (v8.0)](#rag-eval--performance-v80)
    - [Adaptive Intelligence (v9.0)](#adaptive-intelligence-v90)

---

## 1. Before You Begin

### Prerequisites

To use FlowNote, you'll need:

#### ✅ Software
- **Python 3.11+**: Download from [python.org](https://www.python.org/downloads/)
- **Node.js 18+**: Download from [nodejs.org](https://nodejs.org/)
- **Redis**: Install via `brew install redis` on macOS

#### ✅ API Keys
- **OpenAI API Key**: Get from [platform.openai.com](https://platform.openai.com/)
  - GPT-4o model access required
  - Billing information required (usage-based pricing)

#### ✅ Recommended Environment
- **OS**: macOS, Linux, Windows (WSL2 recommended)
- **Memory**: Minimum 8GB RAM
- **Storage**: Minimum 2GB free space

---

## 2. First Run

### 2.1 Project Installation

```bash
# 1. Clone repository
git clone https://github.com/jjaayy2222/flownote-mvp.git
cd flownote-mvp

# 2. Create Python virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install Python packages
pip install -r requirements.txt

# 4. Install Frontend packages
cd web_ui
npm install
cd ..
```

### 2.2 Environment Configuration

```bash
# Create .env file
cp .env.example .env

# Edit .env file (use nano or your preferred editor)
nano .env
```

**Required .env settings:**
```env
# OpenAI API Configuration
OPENAI_API_KEY=sk-your-api-key-here

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Database Path
DATABASE_PATH=./data/flownote.db

# File Storage Path
UPLOAD_DIR=./data/uploads
```

### 2.3 Start Redis Server

```bash
# macOS/Linux
brew services start redis

# Or run directly
redis-server
```

### 2.4 Run Services

**Terminal 1 - Backend API:**
```bash
source venv/bin/activate
python -m uvicorn backend.main:app --reload
# → http://127.0.0.1:8000
```

**Terminal 2 - Frontend:**
```bash
cd web_ui
npm run dev
# → http://localhost:3000
```

**Terminal 3 - Celery Worker (for automation):**
```bash
celery -A backend.celery_app.celery worker --beat --loglevel=info
```

**Terminal 4 - Flower (monitoring, optional):**
```bash
celery -A backend.celery_app.celery flower --port=5555
# → http://localhost:5555
```

---

## 3. Onboarding Process

### 3.1 Access First Screen

Open your browser and navigate to `http://localhost:3000/en`.

### 3.2 Enter User Information

1. **Name**: Enter your name or nickname
2. **Profession**: Enter your current job or role
   - Examples: "Software Developer", "Project Manager", "Student"

### 3.3 Select Interest Areas

AI analyzes your profession and recommends **10 interest areas**.

**Example recommendations (Software Developer):**
- Web Development
- Database Design
- API Development
- DevOps
- Code Review
- Technical Documentation
- Project Management
- Algorithm Learning
- Open Source Contribution
- Performance Optimization

**Select 5 areas** to set up personalized classification criteria.

### 3.4 Complete Onboarding

After selection, you'll be automatically redirected to the dashboard.

---

## 4. Document Classification

### 4.1 Upload Files

1. Navigate to **File Classification** tab
2. Click **Select File** button
3. Choose file to classify (PDF, TXT, MD supported)
4. Click **Start Classification** button

### 4.2 View Classification Results

AI analysis results will be displayed:

```
📋 Classification Result
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Category: Projects
Confidence: 95%
Keywords: project, deadline, goals, plan

Classification Reasoning:
- Clear deadline specified
- Specific goals and deliverables defined
- Project phases and milestones included
```

### 4.3 Understanding PARA Categories

#### 📋 Projects
- **Definition**: Short-term goals with clear deadlines
- **Examples**: "Q1 Marketing Campaign", "Website Redesign"
- **Characteristics**: Clear completion point

#### 🎯 Areas
- **Definition**: Ongoing responsibility areas
- **Examples**: "Team Management", "Health", "Finance"
- **Characteristics**: No end date

#### 📚 Resources
- **Definition**: Reference materials or learning resources
- **Examples**: "Python Tutorial", "Design Guidelines"
- **Characteristics**: Referenced when needed

#### 📦 Archives
- **Definition**: Completed projects or inactive materials
- **Examples**: "2024 Project Results", "Legacy Documentation"
- **Characteristics**: Storage, inactive

### 4.4 Modify Classification

If AI classification is inaccurate:

1. Click **Manual Reclassify** button
2. Select correct category
3. Click **Save** button

---

## 5. Using Search

### 5.1 Keyword Search

1. Navigate to **Search** tab
2. Enter search term (e.g., "API documentation")
3. Press Enter or click **Search** button

### 5.2 Understanding Search Results

```
🔍 Search Results (3 items)

1. REST API Design Guide.pdf
   Category: Resources
   Similarity: 92%
   Keywords: API, REST, design, guide

2. API Development Project Plan.md
   Category: Projects
   Similarity: 87%
   Keywords: API, development, project

3. API Documentation Template.txt
   Category: Resources
   Similarity: 85%
   Keywords: API, documentation, template
```

### 5.3 Advanced Search Tips

- **Exact phrase search**: Use quotes `"REST API"`
- **Category filter**: Search specific PARA categories
- **Date range**: Search files within a specific period

> 💡 **Hybrid RAG Search** is available for more accurate results. See [Chapter 6](#6-hybrid-rag-search) for details.

---

## 6. Hybrid RAG Search

The **Hybrid RAG Search** introduced in FlowNote combines semantic (Dense) and keyword (Sparse) search to deliver significantly more accurate results.

### 6.1 Search Engine Architecture

```
Search Query Input
    ↓
┌─────────────────────────────────┐
│  FAISS (Dense Vector Search)    │  ← Semantic/context-based search
│  BM25  (Sparse Keyword Search)  │  ← Exact keyword matching
└─────────────────────────────────┘
    ↓
  RRF (Reciprocal Rank Fusion)     ← Combines results at optimal ratio
    ↓
  Final Search Results
```

### 6.2 First Time: Building the Initial Index

Before using hybrid search, you need to index your Obsidian Vault.

```bash
# Run from the project root in the terminal
# ✅ First run (no existing index)
python scripts/bootstrap_index.py --vault /path/to/your/vault

# ⚠️  Full rebuild (deletes existing index and rebuilds - irreversible)
python scripts/bootstrap_index.py --vault /path/to/your/vault --clear
```

> 📂 The index is stored in the `data/indices/` directory and is automatically loaded on server restart.

### 6.3 Using Hybrid Search

1. Click **🔍 Hybrid Search** in the dashboard sidebar (`/search` page)
2. Enter your search query in the search bar
3. Configure search parameters:

| Parameter | Description | Recommended |
|-----------|-------------|-------------|
| **alpha** | Dense(FAISS)/Sparse(BM25) weight ratio<br>`1.0` = FAISS only, `0.0` = BM25 only | `0.5` (equal) |
| **k** | Maximum number of results to return | `5` ~ `10` |
| **Category** | Filter results to a specific PARA category | Optional |

### 6.4 Interpreting Search Results

```
🔍 Hybrid Search Results (5 items) | Latency: 120ms

1. Project_Plan_2025.md
   Category: Projects     Score: 0.87
   ──────────────────────────────────
   Preview: "...Q1 2025 milestone roadmap..."

2. API_Design_Guide.pdf
   Category: Resources    Score: 0.82
   ...
```

- **Score**: Final relevance score (0~1) merged by the RRF algorithm
- **Latency**: ≤10ms on Redis cache hit, 100~500ms for first-time search

### 6.5 Performance Optimization Tips

- **Cache utilization**: Identical queries are Redis-cached for 1 hour → instant response on repeat searches
- **alpha tuning**:
  - Technical terms / acronyms → `alpha=0.3` (boost BM25)
  - Concept / semantic search → `alpha=0.7` (boost FAISS)
  - General search → `alpha=0.5` (default)
- **Category filter**: Use when you know the document type to improve precision

---

## 7. AI Assistant Chat

Directly consult with the **AI Assistant**, a core FlowNote feature, to extract insights and answers from your stored knowledge.

### 7.1 Starting a Chat

1. Click the **💬 AI Chat** button at the bottom or in the sidebar of the dashboard to open the chat window.
2. Type your question in the input field at the bottom and press Enter.

### 7.2 Key Features and Characteristics

- **Real-time Streaming (SSE)**: Text is rendered in real-time as it's being generated, minimizing wait times.
- **Intelligent Inline Citations**: Source numbers like `[1]` and `[2]` are displayed within the answer.
  - **Clicking Numbers**: Clicking a citation number opens the `Source Panel` on the right, allowing you to instantly view the original document snippet.
- **Security Guardrails (PII Masking)**: Sensitive personal information (emails, phone numbers) is automatically masked (e.g., `+1-***-***-1234` or `user@****.com`) when detected in answers or sources.
- **Persistent Session Management**: Manages a unique `user_id` via browser `localStorage`, ensuring chat history persists even after closing the browser.

### 7.3 Effective Chatting Tips

- **Be Specific**: Instead of asking "How do I write a project proposal?", try "Summarize the key objectives and milestones of 'Project A' in my Projects category."
- **Consistency**: AI utilizes real-time streaming (SSE) and inline citations to ensure transparency in its knowledge extraction.

---

## 8. Using the Dashboard

### 8.1 Dashboard Overview

The dashboard consists of 3 main sections:

#### 📊 Stats
- **PARA Distribution**: File ratio by category
- **Weekly Trend**: File processing volume for last 12 weeks
- **Activity Heatmap**: GitHub-style annual activity

#### 🌐 Graph View
- **File-Category Relationships**: React Flow-based visualization
- **Node Click**: View file details
- **Zoom/Pan**: Navigate with mouse wheel and drag

#### 🔄 Sync Monitor
- **Obsidian Connection Status**: Real-time display
- **MCP Server Status**: Connection status
- **Last Sync**: Last synchronization time

### 8.2 Real-time Updates

WebSocket-based real-time updates:
- Instant reflection when file classification completes
- Immediate display of sync status changes
- 50% network traffic reduction

---

## 9. Automation Settings

### 9.1 Auto Reclassification

**Configuration location**: `backend/celery_app/config.py`

```python
# Reclassify low-confidence files daily at midnight
'daily-reclassify': {
    'task': 'backend.celery_app.tasks.reclassification.daily_reclassify_tasks',
    'schedule': crontab(hour=0, minute=0),
}
```

**How it works:**
1. Automatically selects files with <70% confidence
2. Reclassifies with latest AI model
3. Records results in logs

### 9.2 Smart Archiving

```python
# Archive old projects every Sunday at midnight
'weekly-archive': {
    'task': 'backend.celery_app.tasks.archiving.weekly_archive_old_projects',
    'schedule': crontab(day_of_week=0, hour=0, minute=0),
}
```

**How it works:**
1. Detects Projects files untouched for 90+ days
2. Suggests moving to Archives
3. Moves after user approval

### 9.3 Monitor with Flower

Check at `http://localhost:5555`:
- Running tasks
- Task success/failure statistics
- Worker status

---

## 10. Obsidian Integration

### 10.1 MCP Server Configuration

**Claude Desktop config file** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "flownote": {
      "command": "python",
      "args": ["-m", "backend.mcp.server"],
      "cwd": "/path/to/flownote-mvp"
    }
  }
}
```

### 10.2 Obsidian Vault Integration

1. **Modify configuration file** (`.env`):
```env
OBSIDIAN_VAULT_PATH=/path/to/your/vault
```

2. **Enable auto-sync**:
```env
OBSIDIAN_AUTO_SYNC=true
SYNC_INTERVAL=300  # Every 5 minutes
```

### 10.3 Conflict Resolution

When file conflicts occur:

1. **Receive notification**: Conflict alert displayed on dashboard
2. **Open Diff Viewer**: Compare changes
3. **Choose resolution method**:
   - **Keep Local**: Keep local version
   - **Keep Remote**: Keep Obsidian version
   - **Keep Both**: Keep both versions (timestamp added to filename)

**Diff Viewer features:**
- Monaco Editor-based Side-by-Side comparison
- Syntax Highlighting
- Markdown Preview
- Inline Diff display

---

## 11. Language Settings

### 11.1 Web UI Language Switching

1. Click **language switcher** in top-right corner
2. Select **한국어** or **English**
3. URL automatically changes (`/ko` ↔ `/en`)
4. UI updates instantly

**Supported languages:**
- Korean (ko)
- English (en)

### 11.2 API Response Language

Set `Accept-Language` header in HTTP requests:

```bash
curl -H "Accept-Language: ko" http://localhost:8000/api/classify
curl -H "Accept-Language: en" http://localhost:8000/api/classify
```

---

## 12. Troubleshooting

### 12.1 Common Issues

#### ❌ Redis Connection Error
```
ConnectionRefusedError: [Errno 61] Connection refused
```

**Solution:**
```bash
# Start Redis server
brew services start redis

# Or
redis-server
```

#### ❌ OpenAI API Error
```
openai.error.AuthenticationError: Incorrect API key provided
```

**Solution:**
1. Check `OPENAI_API_KEY` in `.env` file
2. Remove leading/trailing spaces from API key
3. Verify key validity at [platform.openai.com](https://platform.openai.com/)

#### ❌ Port Conflict
```
Error: listen EADDRINUSE: address already in use :::8000
```

**Solution:**
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

#### ❌ WebSocket Connection Failed
```
WebSocket connection failed
```

**Solution:**
1. Verify Backend API is running
2. Check error messages in browser console
3. Check firewall settings

### 12.2 Check Logs

**Backend logs:**
```bash
# Uvicorn logs
tail -f logs/uvicorn.log

# Celery logs
tail -f logs/celery.log
```

**Frontend logs:**
```bash
# Next.js development server logs
cd web_ui
npm run dev
```

### 12.3 Database Reset

**Warning: All data will be deleted!**

```bash
# Delete database file
rm data/flownote.db

# Delete uploaded files
rm -rf data/uploads/*

# Restart server
python -m uvicorn backend.main:app --reload
```

### 12.4 Hybrid Search Troubleshooting

#### ❌ No results or irrelevant results
**Cause**: Index not built or outdated index

**Solution**:
```bash
# Rebuild index (delete existing index and rebuild)
python scripts/bootstrap_index.py --vault /path/to/your/vault --clear
```

#### ❌ Slow search response
**Cause**: Redis not running → cache inactive, or large Vault

**Solution**:
```bash
# Check if Redis is running
redis-cli ping  # PONG means it's working

# Restart Redis
brew services restart redis
```

#### ❌ Index loading error (on server start)
```
OSError: [Errno 2] No such file or directory: 'data/indices/...'
```
**Solution**: Run `bootstrap_index.py` to build the initial index, then restart the server

#### ❌ OpenAI API error (during indexing)
```
openai.RateLimitError: Rate limit exceeded
```
**Solution**: Reduce concurrent requests with `--concurrency`
```bash
python scripts/bootstrap_index.py --vault /path/to/your/vault --concurrency 2
```

### 12.5 AI Assistant Chat Troubleshooting

#### ❌ Citation numbers [n] appear but clicking them does nothing
**Cause**: Source data loading failure or regex parsing error.
**Solution**: Refresh the page (F5) and try asking again. If the issue persists, check the `web_ui` logs.

#### ❌ Question submitted but no answer is returned
**Cause**: Backend API server not running or OpenAI API quota exceeded.
**Solution**: Check the server logs in `Terminal 1` for any error messages.

### 12.6 Get Support

- **GitHub Issues**: [github.com/jjaayy2222/flownote-mvp/issues](https://github.com/jjaayy2222/flownote-mvp/issues)
- **Email**: qkfkadmlEkf@gmail.com
- **Documentation**: [README_EN.md](./README_EN.md)

---

---

## 13. 🛠️ Technical & Developer Appendix

This section contains technical details about RAG quality evaluation and autonomous learning engines.

### RAG Eval & Performance (v8.0)

> [!IMPORTANT]
> **For Developers**: Tools to measure RAG system reliability and maximize throughput.

#### 1. Golden Dataset Extraction
Automatically generates 'Ground Truth' based on user feedback labels.

#### 2. Evaluation Framework
```bash
# Measure E2E Search Quality
pytest tests/e2e/test_rag_search_quality.py -s -v
```

#### 3. Performance Tuning
- LLM Caching and Redis Pipelining to minimize cold-start latency.

### Adaptive Intelligence (v9.0)

> [!NOTE]
> **Tech Specs**: Autonomous engine evolving based on user data patterns.

#### 1. Adaptive Fine-tuning
Manages OpenAI Fine-tuning Jobs to continuously improve classification precision.

#### 2. Observability
- Leverages structured tags (`ObsEvent`, `ObsMetaTag`) for auditing autonomous system actions.

---

<p align="center">
  <strong>FlowNote</strong> - Start efficient document management today! 🚀
</p>
