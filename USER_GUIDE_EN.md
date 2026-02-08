# 📖 FlowNote User Guide

<p align="center">
  <a href="./USER_GUIDE.md">한국어</a> | <a href="./USER_GUIDE_EN.md"><strong>English</strong></a>
</p>

> New to FlowNote? Follow this guide to get started!

---

## 📖 Table of Contents

1. [Before You Begin](#1-before-you-begin)
2. [First Run](#2-first-run)
3. [Onboarding Process](#3-onboarding-process)
4. [Classifying Files](#4-classifying-files)
5. [Using Search](#5-using-search)
6. [Dashboard Features](#6-dashboard-features)
7. [Automation Settings](#7-automation-settings)
8. [Obsidian Integration](#8-obsidian-integration)
9. [Language Settings](#9-language-settings)
10. [Troubleshooting](#10-troubleshooting)

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

## 4. Classifying Files

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
- **Date range**: Search files within specific period

---

## 6. Dashboard Features

### 6.1 Dashboard Overview

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

### 6.2 Real-time Updates (v6.0)

WebSocket-based real-time updates:
- Instant reflection when file classification completes
- Immediate display of sync status changes
- 50% network traffic reduction

---

## 7. Automation Settings

### 7.1 Auto Reclassification

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

### 7.2 Smart Archiving

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

### 7.3 Monitor with Flower

Check at `http://localhost:5555`:
- Running tasks
- Task success/failure statistics
- Worker status

---

## 8. Obsidian Integration

### 8.1 MCP Server Configuration

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

### 8.2 Obsidian Vault Integration

1. **Modify configuration file** (`.env`):
```env
OBSIDIAN_VAULT_PATH=/path/to/your/vault
```

2. **Enable auto-sync**:
```env
OBSIDIAN_AUTO_SYNC=true
SYNC_INTERVAL=300  # Every 5 minutes
```

### 8.3 Conflict Resolution (v6.0)

When file conflicts occur:

1. **Receive notification**: Conflict alert displayed on dashboard
2. **Open Diff Viewer**: Compare changes
3. **Choose resolution method**:
   - **Keep Local**: Keep local version
   - **Keep Remote**: Keep Obsidian version
   - **Keep Both**: Keep both versions (timestamp added to filename)

**Diff Viewer features (v6.0):**
- Monaco Editor-based Side-by-Side comparison
- Syntax Highlighting
- Markdown Preview
- Inline Diff display

---

## 9. Language Settings

### 9.1 Web UI Language Switching (v6.0)

1. Click **language switcher** in top-right corner
2. Select **한국어** or **English**
3. URL automatically changes (`/ko` ↔ `/en`)
4. UI updates instantly

**Supported languages:**
- Korean (ko)
- English (en)

### 9.2 API Response Language

Set `Accept-Language` header in HTTP requests:

```bash
curl -H "Accept-Language: ko" http://localhost:8000/api/classify
curl -H "Accept-Language: en" http://localhost:8000/api/classify
```

---

## 10. Troubleshooting

### 10.1 Common Issues

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

#### ❌ WebSocket Connection Failed (v6.0)
```
WebSocket connection failed
```

**Solution:**
1. Verify Backend API is running
2. Check error messages in browser console
3. Check firewall settings

### 10.2 Check Logs

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

### 10.3 Database Reset

**Warning: All data will be deleted!**

```bash
# Delete database file
rm data/flownote.db

# Delete uploaded files
rm -rf data/uploads/*

# Restart server
python -m uvicorn backend.main:app --reload
```

### 10.4 Get Support

- **GitHub Issues**: [github.com/jjaayy2222/flownote-mvp/issues](https://github.com/jjaayy2222/flownote-mvp/issues)
- **Email**: qkfkadmlEkf@gmail.com
- **Documentation**: [README_EN.md](./README_EN.md)

---

## 📚 Additional Resources

- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **Phase Documentation**: `docs/P/` directory
  - [v6.0 Phase 1: WebSocket](docs/P/v6.0_phase1_websocket/)
  - [v6.0 Phase 2: Diff Viewer](docs/P/v6.0_phase2_diff_viewer/)
  - [v6.0 Phase 3: i18n](docs/P/v6.0_phase3_i18n/)

---

<p align="center">
  <strong>FlowNote</strong> - Start efficient document management today! 🚀
</p>
