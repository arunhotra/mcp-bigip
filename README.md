# BIG-IP MCP Server

A Model Context Protocol (MCP) server for managing F5 BIG-IP devices. Built with FastMCP 2.0, this server provides tools to authenticate to BIG-IP load balancers and query virtual server configurations.

## Features

- **Configuration-Based Credentials** - Store BIG-IP credentials securely in a JSON config file
- **Multi-Device Support** - Manage multiple BIG-IP devices from a single server
- **Token Caching** - Automatically caches authentication tokens and reuses until expiry
- **Virtual Server Management** - List all virtual servers with status and configuration
- **AS3 Management** - Check, install, and upgrade F5 Application Services 3 Extension
- **SSL Flexibility** - Support for self-signed certificates (common in lab environments)
- **Async/Await** - Non-blocking I/O for responsive performance

## Quick Start

1. **Install dependencies** (see Installation section below)
2. **Create configuration file:**
   ```bash
   cp bigip_config.example.json bigip_config.json
   ```
3. **Edit `bigip_config.json`** with your BIG-IP device details
4. **Restart Claude Desktop** to load the server
5. **Use the tools:** Ask Claude to "list BIG-IP devices" or "list virtual servers on [device-name]"

## Installation

### Step 1: Create a Virtual Environment

#### Using venv (recommended for standard Python)

```bash
# Create virtual environment
python -m venv venv

# Activate on macOS/Linux
source venv/bin/activate

# Activate on Windows
venv\Scripts\activate
```

#### Using uv (recommended for modern Python projects)

```bash
# Create virtual environment with uv
uv venv

# Activate on macOS/Linux
source .venv/bin/activate

# Activate on Windows
.venv\Scripts\activate
```

### Step 2: Install Dependencies

With virtual environment activated:

#### Using uv

```bash
uv pip install -r requirements.txt
```

#### Using pip

```bash
pip install -r requirements.txt
```

### Step 3: Verification

Confirm FastMCP is installed:

```bash
fastmcp version
```

**Note:** Always activate your virtual environment before running the server or installing packages.

## Running the Server

**Important:** Make sure your virtual environment is activated before running the server.

### Method 1: Direct execution (stdio transport)

```bash
# Ensure venv is activated first
source venv/bin/activate  # or source .venv/bin/activate for uv

python server.py
```

### Method 2: FastMCP CLI

Run with stdio transport (default for MCP):

```bash
# Ensure venv is activated first
source venv/bin/activate

fastmcp run server.py:mcp
```

Run with HTTP transport:

```bash
fastmcp run server.py:mcp --transport http --port 8000
```

## Configuration

### Creating Your Configuration File

1. Copy the example configuration:
   ```bash
   cp bigip_config.example.json bigip_config.json
   ```

2. Edit `bigip_config.json` with your BIG-IP devices:
   ```json
   {
     "devices": {
       "prod-lb-01": {
         "ip_address": "10.1.1.10",
         "username": "admin",
         "password": "your-password",
         "verify_ssl": false,
         "description": "Production load balancer"
       },
       "lab-bigip": {
         "ip_address": "192.168.1.100",
         "username": "admin",
         "password": "admin",
         "verify_ssl": false,
         "description": "Lab environment"
       }
     }
   }
   ```

3. **Security Note:** `bigip_config.json` is automatically excluded from git (.gitignore)

See [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration guide.

## Available Tools

### `list_bigip_devices`
List all configured BIG-IP devices from the configuration file.

**Usage:**
```
Show me the configured BIG-IP devices
```

**Returns:** List of device names, IP addresses, and descriptions

### `list_virtual_servers`
List all virtual servers on a specific BIG-IP device.

**Parameters:**
- `device_name` - Name of the device from config file (e.g., 'prod-lb-01')

**Usage:**
```
List virtual servers on prod-lb-01
```

**Returns:** Formatted list of virtual servers with status, destination, and configuration details

**Features:**
- Reads credentials from configuration file (no passwords in chat!)
- Automatically authenticates and caches token
- Token reused for 19 minutes before re-authentication

### `manage_as3`
Check, install, or upgrade F5 AS3 (Application Services 3 Extension) on BIG-IP devices.

**Parameters:**
- `device_name` - Name of the device from config file (e.g., 'prod-lb-01')
- `action` - Action to perform: "check" (default), "install", or "upgrade"
- `auto_install` - Set to True to proceed with installation/upgrade (default: False)

**Usage:**
```
Check AS3 status on prod-lb-01
Install AS3 on lab-bigip
Upgrade AS3 on prod-lb-01
```

**Returns:** AS3 version information and installation/upgrade results

**Features:**
- Automatically fetches latest AS3 version from GitHub
- Downloads and uploads RPM to BIG-IP
- Polls installation task until completion
- Verifies installation after completion
- Supports version comparison and upgrade recommendations
- Two-step confirmation with `auto_install` parameter prevents accidental installations

**Requirements:**
- AS3 installation requires admin account (not just administrator role)
- Network access to GitHub for downloading RPM packages
- BIG-IP 14.1+ recommended for AS3 3.50+

### Resources

- **`config://server`** - Server configuration and capabilities

### Prompts

- **`help_prompt()`** - Overview of server capabilities and usage

## Usage with Claude Desktop

Add this server to your Claude Desktop configuration:

### macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
### Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Recommended: Using the wrapper script (avoids permission issues)**

```json
{
  "mcpServers": {
    "bigip": {
      "command": "/Users/a.ganti/Documents/code/mcp-servers/big-ip/run_server.sh"
    }
  }
}
```

The wrapper script automatically handles virtual environment activation and works around macOS permission restrictions.

**Alternative options (if you have permission issues):**

<details>
<summary>Option 1: Direct Python from virtual environment</summary>

```json
{
  "mcpServers": {
    "bigip": {
      "command": "/Users/a.ganti/Documents/code/mcp-servers/big-ip/venv/bin/python",
      "args": ["/Users/a.ganti/Documents/code/mcp-servers/big-ip/server.py"]
    }
  }
}
```
</details>

<details>
<summary>Option 2: FastMCP CLI from virtual environment</summary>

```json
{
  "mcpServers": {
    "bigip": {
      "command": "/Users/a.ganti/Documents/code/mcp-servers/big-ip/venv/bin/fastmcp",
      "args": ["run", "/Users/a.ganti/Documents/code/mcp-servers/big-ip/server.py:mcp"]
    }
  }
}
```
</details>

**Note:** Update the paths above to match your actual installation directory. If using `uv`, change `venv` to `.venv` in the paths.

After updating the config, restart Claude Desktop to load the server.

## Using the BIG-IP Tools

### Example Interactions

**List Available Devices:**
```
Show me the configured BIG-IP devices
```

**List Virtual Servers:**
```
List virtual servers on prod-lb-01
```

Or more naturally:
```
Can you show me the virtual servers on the lab-bigip device?
```

**Check Multiple Devices:**
```
List virtual servers on prod-lb-01 and then on prod-lb-02
```

**Check AS3 Status:**
```
Check AS3 status on prod-lb-01
```

**Install AS3:**
```
Install AS3 on lab-bigip
```

**Upgrade AS3:**
```
Upgrade AS3 on prod-lb-01 if a newer version is available
```

### Workflow

1. **First time:** Create and configure `bigip_config.json` with your devices
2. **Check devices:** Ask Claude to list available BIG-IP devices
3. **Query virtual servers:** Specify the device name from your config
4. **Credentials:** Read automatically from config file (no passwords in chat!)
5. **Subsequent requests:** Authentication tokens cached for efficiency

## BIG-IP Requirements

### Network Access
- The machine running this MCP server must have network access to the BIG-IP management interface (typically port 443/HTTPS)
- Ensure firewall rules allow outbound HTTPS connections to your BIG-IP device

### BIG-IP Configuration
- BIG-IP must have iControl REST API enabled (enabled by default)
- User account must have appropriate permissions to:
  - Authenticate via iControl REST
  - Read virtual server configurations (typically requires at least "Guest" role)

### Supported Versions
- BIG-IP version 12.0 or higher (for token-based authentication)
- Tested with BIG-IP 13.x, 14.x, 15.x, 16.x, 17.x

### SSL Certificates
- For production BIG-IP devices with valid SSL certificates, set `verify_ssl: true`
- For lab/dev environments with self-signed certificates, use `verify_ssl: false` (default)

## Security Considerations

### Credential Handling
- **Never hardcoded** - Credentials are requested interactively via MCP's elicitation feature
- **Session-scoped caching** - Credentials are cached only for the current MCP session
- **Token-based auth** - Password is only sent during initial authentication; subsequent requests use tokens
- **Automatic expiry** - Tokens expire after 19 minutes and are automatically refreshed

### Best Practices
1. Use dedicated service accounts with read-only permissions when possible
2. Enable SSL verification (`verify_ssl: true`) for production environments
3. Use the `clear_bigip_credentials` tool when switching between BIG-IP devices
4. Ensure Claude Desktop has appropriate file permissions (see Troubleshooting)

## Troubleshooting

### Permission Errors with Virtual Environment

If you see errors like `PermissionError: [Errno 1] Operation not permitted: '/path/to/venv/pyvenv.cfg'`:

1. **Use the wrapper script** (recommended):
   ```json
   {
     "mcpServers": {
       "bigip": {
         "command": "/Users/a.ganti/Documents/code/mcp-servers/big-ip/run_server.sh"
       }
     }
   }
   ```

2. **Grant Claude Desktop Full Disk Access**:
   - Open System Settings → Privacy & Security → Full Disk Access
   - Add Claude and enable access
   - Restart Claude Desktop

3. **Or recreate the virtual environment**:
   ```bash
   rm -rf venv
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### BIG-IP Connection Issues

**"Failed to connect to BIG-IP"**
- Verify network connectivity: `ping <bigip-ip>`
- Verify HTTPS access: `curl -k https://<bigip-ip>/mgmt/shared/authn/login`
- Check firewall rules allow outbound HTTPS (port 443)

**"Authentication failed: 401"**
- Verify username and password are correct
- Check user account is enabled in BIG-IP
- Verify user has API access permissions

**"SSL verification failed"**
- For self-signed certificates, set `verify_ssl: false` when prompted
- For production, ensure BIG-IP has valid SSL certificate

**"Failed to retrieve virtual servers: 403"**
- User account lacks permissions to read LTM configuration
- Requires at least "Guest" role or custom role with `ltm` read permissions

### Server Not Connecting

Check the Claude Desktop logs for errors. The wrapper script provides better error handling and environment isolation.

## Development

### Adding More Tools

To add additional BIG-IP management capabilities:

1. Create a new async function using the `@mcp.tool` decorator
2. Use `ctx: Context` parameter for logging and elicitation
3. Reuse cached credentials from context state
4. Follow the pattern in `list_virtual_servers` for authentication

Example:
```python
@mcp.tool
async def list_pools(ctx: Context) -> str:
    """List all load balancing pools"""
    # Get cached credentials
    credentials = ctx.get_state("bigip_credentials")
    token = ctx.get_state("bigip_token")

    # Your implementation here
    ...
```

### Extending Functionality

Additional F5 BIG-IP operations that could be added:
- List pool members and their status
- Query pool statistics
- List iRules
- Get SSL certificate information
- Query virtual server statistics
- List nodes and their availability

## Documentation

- **FastMCP**: https://gofastmcp.com
- **MCP Protocol**: https://modelcontextprotocol.io
- **F5 BIG-IP iControl REST API**: https://clouddocs.f5.com/api/icontrol-rest/
- **F5 LTM Virtual Server API**: https://clouddocs.f5.com/api/icontrol-rest/APIRef_tm_ltm_virtual.html

## License

This project is provided as-is for managing F5 BIG-IP devices via the MCP protocol.
