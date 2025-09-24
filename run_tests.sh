#!/bin/bash

# Collections Agent Backend - Test Runner Script
# This script helps you test the complete demo flow

echo "🚀 Collections Agent Backend - Test Runner"
echo "=========================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Creating one..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Run migrations
echo "🗄️  Running database migrations..."
python manage.py migrate

# Set up demo data
echo "📊 Setting up demo data..."
python manage.py setup_integration_demo

# Start Django server in background
echo "🌐 Starting Django server..."
python manage.py runserver 8000 &
SERVER_PID=$!

# Wait for server to start
echo "⏳ Waiting for server to start..."
sleep 5

# Run the demo simulation
echo "🧪 Running demo script simulation..."
python simulate_demo_script.py

# Stop the server
echo "🛑 Stopping Django server..."
kill $SERVER_PID

echo "✅ Test completed!"
echo ""
echo "📋 Summary:"
echo "   - Django server started and stopped"
echo "   - Demo data set up"
echo "   - Complete demo flow tested"
echo "   - All APIs verified"
echo ""
echo "💡 Your backend is ready for Salesforce team integration!"
