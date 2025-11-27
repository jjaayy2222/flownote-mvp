#!/bin/bash

# ------------------------------------------------------------------------------
# FlowNote Startup Script
# ------------------------------------------------------------------------------

echo "🚀 Starting FlowNote MVP..."

# 1. Create necessary directories
echo "📂 Creating directories..."
mkdir -p data/vector_store
mkdir -p data/logs
mkdir -p data/users
mkdir -p temp

# 2. Check environment variables
if [ -z "$GPT4O_MINI_API_KEY" ]; then
    echo "⚠️  WARNING: GPT4O_MINI_API_KEY is not set!"
fi

# 3. Start Gunicorn Server
echo "🔥 Starting Gunicorn server..."
exec gunicorn backend.main:app -c gunicorn_conf.py
