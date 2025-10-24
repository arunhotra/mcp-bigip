#!/bin/bash

# BigIP MCP Server Setup Script
# This script creates a virtual environment and installs dependencies

set -e  # Exit on error

echo "BigIP MCP Server Setup"
echo "======================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

echo "Python version: $(python3 --version)"
echo ""

# Ask user for venv tool preference
echo "Choose virtual environment tool:"
echo "1) venv (standard Python)"
echo "2) uv (modern, faster)"
read -p "Enter choice [1-2] (default: 1): " choice
choice=${choice:-1}

echo ""

# Create virtual environment based on choice
if [ "$choice" == "2" ]; then
    if ! command -v uv &> /dev/null; then
        echo "Error: uv is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    echo "Creating virtual environment with uv..."
    uv venv
    VENV_PATH=".venv"
    ACTIVATE_PATH=".venv/bin/activate"
else
    echo "Creating virtual environment with venv..."
    python3 -m venv venv
    VENV_PATH="venv"
    ACTIVATE_PATH="venv/bin/activate"
fi

echo "Virtual environment created at: $VENV_PATH"
echo ""

# Activate and install dependencies
echo "Installing dependencies..."
source "$ACTIVATE_PATH"

if [ "$choice" == "2" ]; then
    uv pip install fastmcp
else
    pip install -r requirements.txt
fi

echo ""
echo "Setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source $ACTIVATE_PATH"
echo ""
echo "To run the server:"
echo "  python server.py"
echo ""
echo "To verify installation:"
echo "  fastmcp version"
echo ""
