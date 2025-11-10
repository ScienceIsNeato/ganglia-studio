#!/bin/bash
# Setup script for ganglia-studio

set -e

echo "🎬 Setting up ganglia-studio..."

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d'.' -f1,2)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements-dev.txt

# Copy config template if config doesn't exist
if [ ! -f "config/ttv_config.json" ]; then
    echo "📋 Creating config/ttv_config.json from template..."
    cp config/ttv_config.template.json config/ttv_config.json
    echo "✓ Edit config/ttv_config.json to customize your video generation settings"
fi

# Copy envrc template if .envrc doesn't exist
if [ ! -f ".envrc" ]; then
    echo "🔑 Creating .envrc from template..."
    cp .envrc.template .envrc
    echo "⚠️  IMPORTANT: Edit .envrc and add your API keys!"
    echo "   Then run: source .envrc"
fi

# Create output directories
mkdir -p generated_videos logs

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .envrc with your API keys"
echo "2. Run: source .envrc"
echo "3. Edit config/ttv_config.json to customize your video"
echo "4. Run: ganglia-studio video --config config/ttv_config.json"
echo ""

