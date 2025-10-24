# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Model Context Protocol (MCP) server** for managing F5 BIG-IP load balancers, built with FastMCP 2.0. It exposes BIG-IP management capabilities (virtual server listing, authentication) to MCP-compatible clients like Claude Desktop.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# OR
uv venv && source .venv/bin/activate  # Using uv

# Install dependencies
pip install -r requirements.txt
```

### Running the Server

```bash
# Method 1: Direct execution (requires venv activated)
python server.py

# Method 2: Using FastMCP CLI (requires venv activated)
fastmcp run server.py:mcp

# Method 3: HTTP transport for testing
fastmcp run server.py:mcp --transport http --port 8000

# Method 4: Wrapper script (handles venv automatically)
./run_server.sh
```

### Configuration Management

```bash
# Create config from template (first time setup)
cp bigip_config.example.json bigip_config.json

# Validate server starts without errors
python server.py --help
```

### Testing with Claude Desktop

The server integrates with Claude Desktop via `claude_desktop_config.json`. After code changes:
1. Quit Claude Desktop completely (`Cmd+Q` on macOS)
2. Reopen Claude Desktop
3. Server auto-reloads with new changes

Check logs at `~/Library/Logs/Claude/mcp-server-bigip.log` (macOS)

## Architecture

### Core Components

**Configuration Layer** (`server.py:62-123`)
- `load_bigip_config()` - Loads multi-device config from `bigip_config.json`
- `get_device_by_name()` - Retrieves specific device credentials
- Config file structure: `{"devices": {"name": {ip, username, password, verify_ssl, description}}}`

**Authentication Flow** (`server.py:130-174`)
- `authenticate_bigip()` - Authenticates to BIG-IP iControl REST API
  - Endpoint: `POST https://{bigip}/mgmt/shared/authn/login`
  - Returns: Token valid for 1200 seconds (cached for 1140s/19min)
  - Uses TMOS login provider

**API Integration** (`server.py:177-226`)
- `get_virtual_servers()` - Queries BIG-IP virtual server endpoint
  - Endpoint: `GET https://{bigip}/mgmt/tm/ltm/virtual`
  - Auth: `X-F5-Auth-Token` header
  - Returns: List of VirtualServer Pydantic models

**MCP Tools** (`server.py:233-336`)
- `list_virtual_servers(device_name)` - Main tool for querying virtual servers
  - Reads credentials from config (no passwords in prompts)
  - Implements token caching via `ctx.set_state()`/`ctx.get_state()`
  - Tokens cached per-device with key `bigip_token_{device_name}`

- `list_bigip_devices()` - Lists all configured devices from config file

### Key Design Decisions

**Why Configuration File vs User Elicitation:**
- Claude Desktop doesn't support `ctx.elicit()` (MCP user elicitation feature)
- Config file approach keeps passwords out of chat logs
- Supports multiple devices without re-entering credentials

**Token Caching Strategy:**
- Tokens stored in MCP Context state (session-scoped, not persistent)
- Keyed by device name, not IP (allows IP changes without breaking cache)
- Expires 1 minute before BIG-IP token expiry to prevent auth failures

**SSL Verification:**
- Default `verify_ssl=false` for lab environments with self-signed certs
- Production devices should set `verify_ssl=true` in config

### Data Models (Pydantic)

```python
BIGIPDevice      # Config file device entry (ip, username, password, verify_ssl, description)
BIGIPCredentials # Runtime credentials (ip, username, password, verify_ssl)
AuthToken        # Cached token (token, expires_at)
VirtualServer    # API response (name, full_path, destination, enabled, availability_status, description)
```

## Common Modifications

### Adding New BIG-IP API Endpoints

1. Add async helper function following `get_virtual_servers()` pattern
2. Use `httpx.AsyncClient` with token in `X-F5-Auth-Token` header
3. Create Pydantic model for response data
4. Add `@mcp.tool` decorated function that:
   - Takes `device_name: str` parameter
   - Calls `get_device_by_name()` for credentials
   - Checks for cached token via `ctx.get_state(f"bigip_token_{device_name}")`
   - Uses your helper function with token
   - Returns formatted string response

Example endpoints to add:
- `/mgmt/tm/ltm/pool` - List load balancing pools
- `/mgmt/tm/ltm/pool/{name}/members` - List pool members
- `/mgmt/tm/ltm/rule` - List iRules
- `/mgmt/tm/sys/provision` - List provisioned modules

### Modifying Token Expiry

Change line 168 in `authenticate_bigip()`:
```python
expires_at = datetime.now() + timedelta(seconds=1140)  # 19 minutes
```

### Adding New Configuration Fields

1. Update `BIGIPDevice` Pydantic model (line 29)
2. Update `bigip_config.example.json`
3. Update `CONFIGURATION.md` with field documentation

## File Structure

```
server.py                    # Main MCP server (all logic in single file)
bigip_config.json            # User's device credentials (gitignored)
bigip_config.example.json    # Template for config file
run_server.sh                # Wrapper script for Claude Desktop integration
requirements.txt             # Python dependencies (fastmcp, httpx, pydantic)
README.md                    # User documentation
CONFIGURATION.md             # Detailed config guide
```

## Important Constraints

- **No user elicitation**: Claude Desktop doesn't support `ctx.elicit()` - use config files or tool parameters
- **macOS permissions**: Claude Desktop may need Full Disk Access for venv access; wrapper script mitigates this
- **Session-scoped state**: `ctx.set_state()` is per-session, not persistent across server restarts
- **FastMCP 2.0**: Uses newer FastMCP (not official MCP SDK's FastMCP 1.0)
- **BIG-IP version**: Requires BIG-IP 12.0+ for token-based authentication
