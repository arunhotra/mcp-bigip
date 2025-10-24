#!/bin/bash
# Wrapper script to run the MCP server with proper environment

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Try to use virtual environment if it exists and works
if [ -d "$DIR/venv" ]; then
    export VIRTUAL_ENV="$DIR/venv"
    export PATH="$DIR/venv/bin:$PATH"
    exec "$DIR/venv/bin/python" "$DIR/server.py" "$@"
elif [ -d "$DIR/.venv" ]; then
    export VIRTUAL_ENV="$DIR/.venv"
    export PATH="$DIR/.venv/bin:$PATH"
    exec "$DIR/.venv/bin/python" "$DIR/server.py" "$@"
else
    # Fall back to system Python with pip install --user fastmcp
    exec python3 "$DIR/server.py" "$@"
fi
