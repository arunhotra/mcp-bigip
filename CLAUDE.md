# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Model Context Protocol (MCP) server** for managing F5 BIG-IP load balancers, built with FastMCP 2.0. It exposes BIG-IP management capabilities (virtual server listing, AS3 extension management, authentication) to MCP-compatible clients like Claude Desktop.

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

**AS3 Management Helpers** (`server.py:235-490`)
- `get_latest_as3_release()` - Fetches latest AS3 version from GitHub API
  - Endpoint: `GET https://api.github.com/repos/F5Networks/f5-appsvcs-extension/releases/latest`
  - Returns: version, rpm_url, rpm_filename, sha256_url
- `check_as3_installed()` - Checks if AS3 is installed and returns version
  - Endpoint: `GET https://{bigip}/mgmt/shared/appsvcs/info`
  - Returns: Version string or None if not installed
- `download_as3_rpm()` - Downloads AS3 RPM from GitHub
- `upload_as3_rpm()` - Uploads RPM to BIG-IP file transfer endpoint
  - Endpoint: `POST https://{bigip}/mgmt/shared/file-transfer/uploads/{filename}`
  - Uses Content-Range header for file size
- `install_as3_package()` - Installs RPM and polls until complete
  - Endpoint: `POST https://{bigip}/mgmt/shared/iapp/package-management-tasks`
  - Polls task status every 5 seconds with 5-minute timeout

**MCP Tools** (`server.py:492-974`)
- `list_virtual_servers(device_name)` - Main tool for querying virtual servers
  - Reads credentials from config (no passwords in prompts)
  - Implements token caching via `ctx.set_state()`/`ctx.get_state()`
  - Tokens cached per-device with key `bigip_token_{device_name}`
  - Returns markdown table with status indicators

- `list_bigip_devices()` - Lists all configured devices from config file

- `manage_as3(device_name, action, auto_install)` - Manages AS3 installation/upgrades
  - Actions: "check" (default), "install", "upgrade"
  - Two-step confirmation: requires `auto_install=True` to proceed
  - Fetches latest AS3 from GitHub automatically
  - Compares installed vs available versions
  - Handles download → upload → install → verify workflow
  - Requires admin account (not just administrator role)

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

**AS3 Management:**
- Always fetches latest version from GitHub (no version pinning)
- Two-step confirmation prevents accidental installations (`auto_install` parameter)
- Polls installation status to provide real-time feedback
- Admin account required (detected via 401/403 errors with clear messaging)
- GitHub download happens on MCP server (not BIG-IP), then uploaded
- 5-minute timeout for installations (typical install: 2-5 minutes)

### Data Models (Pydantic)

```python
BIGIPDevice      # Config file device entry (ip, username, password, verify_ssl, description)
BIGIPCredentials # Runtime credentials (ip, username, password, verify_ssl)
AuthToken        # Cached token (token, expires_at)
VirtualServer    # API response (name, full_path, destination, pool, enabled, availability_status, description)
```

Note: AS3 management uses Dict types for GitHub API responses (no dedicated Pydantic models).

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

### Modifying AS3 Version Selection

Current implementation always fetches latest from GitHub. To pin to specific version:

1. Modify `get_latest_as3_release()` to accept optional version parameter
2. If version specified, construct GitHub release URL: `https://api.github.com/repos/F5Networks/f5-appsvcs-extension/releases/tags/v{version}`
3. Update `manage_as3` tool to accept `version` parameter
4. Document version format in tool docstring (e.g., "3.54.2")

### Adding AS3 Uninstall Capability

1. Add `uninstall_as3_package()` helper function
2. Use same package-management-tasks endpoint with `"operation": "UNINSTALL"`
3. Package name format: `f5-appsvcs-{version}.noarch` (extract from RPM filename)
4. Add "uninstall" action to `manage_as3` tool
5. Require `auto_install=True` confirmation for uninstall

### Adding AS3 Declaration Deployment

AS3 uses `/mgmt/shared/appsvcs/declare` endpoint for deploying configurations:
1. Create new tool `deploy_as3(device_name, declaration)`
2. `declaration` parameter should accept JSON string or dict
3. POST declaration to `/mgmt/shared/appsvcs/declare`
4. Poll `/mgmt/shared/appsvcs/task/{taskId}` for completion
5. Return deployment results

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
