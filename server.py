"""
BIG-IP MCP Server

An MCP server for managing F5 BIG-IP devices. Provides tools to authenticate
and query virtual servers from BIG-IP load balancers.
"""

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import httpx
from datetime import datetime, timedelta
import json
import os
from pathlib import Path


# Initialize the FastMCP server
mcp = FastMCP("BIG-IP MCP Server")

# Configuration file path
CONFIG_FILE = Path(__file__).parent / "bigip_config.json"


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class BIGIPDevice(BaseModel):
    """BIG-IP device configuration"""
    ip_address: str = Field(description="BIG-IP management IP address or hostname")
    username: str = Field(description="BIG-IP username")
    password: str = Field(description="BIG-IP password")
    verify_ssl: bool = Field(default=False, description="Verify SSL certificates (use False for self-signed certs)")
    description: Optional[str] = Field(default=None, description="Device description")


class BIGIPCredentials(BaseModel):
    """Credentials for connecting to BIG-IP"""
    ip_address: str = Field(description="BIG-IP management IP address or hostname")
    username: str = Field(description="BIG-IP username")
    password: str = Field(description="BIG-IP password")
    verify_ssl: bool = Field(default=False, description="Verify SSL certificates (use False for self-signed certs)")


class AuthToken(BaseModel):
    """Authentication token with expiry"""
    token: str
    expires_at: datetime


class VirtualServer(BaseModel):
    """BIG-IP Virtual Server information"""
    name: str
    full_path: str
    destination: str
    enabled: bool
    availability_status: str
    description: Optional[str] = None


# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================

def load_bigip_config() -> Dict[str, BIGIPDevice]:
    """
    Load BIG-IP device configurations from bigip_config.json

    Returns:
        Dictionary mapping device names to BIGIPDevice objects

    Raises:
        Exception: If config file doesn't exist or is invalid
    """
    if not CONFIG_FILE.exists():
        raise Exception(
            f"Configuration file not found: {CONFIG_FILE}\n"
            f"Please create bigip_config.json from bigip_config.example.json"
        )

    try:
        with open(CONFIG_FILE, 'r') as f:
            config_data = json.load(f)

        devices = {}
        for name, device_config in config_data.get("devices", {}).items():
            devices[name] = BIGIPDevice(**device_config)

        if not devices:
            raise Exception("No devices found in configuration file")

        return devices

    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in configuration file: {str(e)}")
    except Exception as e:
        raise Exception(f"Error loading configuration: {str(e)}")


def get_device_by_name(device_name: str) -> BIGIPDevice:
    """
    Get a BIG-IP device configuration by name

    Args:
        device_name: Name of the device in the config file

    Returns:
        BIGIPDevice configuration

    Raises:
        Exception: If device not found
    """
    devices = load_bigip_config()

    if device_name not in devices:
        available = ", ".join(devices.keys())
        raise Exception(
            f"Device '{device_name}' not found in configuration.\n"
            f"Available devices: {available}"
        )

    return devices[device_name]


# ============================================================================
# AUTHENTICATION & API HELPERS
# ============================================================================

async def authenticate_bigip(credentials: BIGIPCredentials) -> AuthToken:
    """
    Authenticate to BIG-IP and obtain an auth token.

    Args:
        credentials: BIG-IP connection credentials

    Returns:
        AuthToken with token string and expiry time

    Raises:
        Exception: If authentication fails
    """
    url = f"https://{credentials.ip_address}/mgmt/shared/authn/login"

    payload = {
        "username": credentials.username,
        "password": credentials.password,
        "loginProviderName": "tmos"
    }

    async with httpx.AsyncClient(verify=credentials.verify_ssl) as client:
        try:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            response.raise_for_status()

            data = response.json()
            token = data["token"]["token"]

            # Default token lifetime is 1200 seconds (20 minutes)
            # Set expiry to 19 minutes to be safe
            expires_at = datetime.now() + timedelta(seconds=1140)

            return AuthToken(token=token, expires_at=expires_at)

        except httpx.HTTPStatusError as e:
            raise Exception(f"BIG-IP authentication failed: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Failed to connect to BIG-IP at {credentials.ip_address}: {str(e)}")


async def get_virtual_servers(
    ip_address: str,
    token: str,
    verify_ssl: bool = False
) -> List[VirtualServer]:
    """
    Retrieve all virtual servers from BIG-IP.

    Args:
        ip_address: BIG-IP management IP
        token: Authentication token
        verify_ssl: Whether to verify SSL certificates

    Returns:
        List of VirtualServer objects

    Raises:
        Exception: If API call fails
    """
    url = f"https://{ip_address}/mgmt/tm/ltm/virtual"

    headers = {
        "X-F5-Auth-Token": token,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(verify=verify_ssl) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()

            data = response.json()
            virtual_servers = []

            for item in data.get("items", []):
                vs = VirtualServer(
                    name=item.get("name", ""),
                    full_path=item.get("fullPath", ""),
                    destination=item.get("destination", ""),
                    enabled=item.get("enabled", False),
                    availability_status=item.get("status", {}).get("availabilityState", "unknown"),
                    description=item.get("description")
                )
                virtual_servers.append(vs)

            return virtual_servers

        except httpx.HTTPStatusError as e:
            raise Exception(f"Failed to retrieve virtual servers: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Error querying BIG-IP: {str(e)}")


# ============================================================================
# MCP TOOLS
# ============================================================================

@mcp.tool
async def list_virtual_servers(
    device_name: str,
    ctx: Context = None
) -> str:
    """
    List all virtual servers configured on the BIG-IP device.

    Args:
        device_name: Name of the BIG-IP device from configuration file
                    (e.g., 'prod-lb-01', 'lab-bigip')

    Returns:
        A formatted list of virtual servers with their status and configuration
    """
    if ctx:
        await ctx.info(f"Starting BIG-IP virtual server query for device: {device_name}")

    # Load device configuration
    try:
        device = get_device_by_name(device_name)
        if ctx:
            await ctx.info(f"Loaded configuration for {device_name} ({device.ip_address})")
    except Exception as e:
        return f"❌ Configuration error: {str(e)}"

    # Create credentials object from config
    credentials = BIGIPCredentials(
        ip_address=device.ip_address,
        username=device.username,
        password=device.password,
        verify_ssl=device.verify_ssl
    )

    # Check if we have a cached valid token for this device
    cached_token = None
    if ctx:
        cached_token = ctx.get_state(f"bigip_token_{device_name}")

    token_obj = None

    # Check if cached token is still valid
    if cached_token:
        token_obj = AuthToken(**cached_token)
        if token_obj.expires_at > datetime.now():
            if ctx:
                await ctx.info("Using cached authentication token")
        else:
            if ctx:
                await ctx.info("Cached token expired, will re-authenticate")
            token_obj = None

    # Authenticate if we don't have a valid token
    if not token_obj:
        if ctx:
            await ctx.info(f"Authenticating to BIG-IP at {credentials.ip_address}")

        try:
            token_obj = await authenticate_bigip(credentials)
            if ctx:
                ctx.set_state(f"bigip_token_{device_name}", token_obj.model_dump())
                await ctx.info("Successfully authenticated to BIG-IP")
        except Exception as e:
            if ctx:
                await ctx.error(f"Authentication failed: {str(e)}")
            return f"❌ Authentication failed: {str(e)}"

    # Query virtual servers
    if ctx:
        await ctx.info("Retrieving virtual servers from BIG-IP")

    try:
        virtual_servers = await get_virtual_servers(
            ip_address=credentials.ip_address,
            token=token_obj.token,
            verify_ssl=credentials.verify_ssl
        )

        if ctx:
            await ctx.info(f"Found {len(virtual_servers)} virtual servers")

        # Format the response
        if not virtual_servers:
            return "No virtual servers found on this BIG-IP device."

        output = [f"Found {len(virtual_servers)} virtual server(s) on BIG-IP {credentials.ip_address}:\n"]

        for vs in virtual_servers:
            status_emoji = "✅" if vs.availability_status == "available" else "❌"
            enabled_text = "enabled" if vs.enabled else "disabled"

            output.append(f"\n{status_emoji} **{vs.name}**")
            output.append(f"  - Full Path: {vs.full_path}")
            output.append(f"  - Destination: {vs.destination}")
            output.append(f"  - Status: {vs.availability_status} ({enabled_text})")
            if vs.description:
                output.append(f"  - Description: {vs.description}")

        return "\n".join(output)

    except Exception as e:
        if ctx:
            await ctx.error(f"Failed to retrieve virtual servers: {str(e)}")
        return f"❌ Failed to retrieve virtual servers: {str(e)}"
@mcp.tool
async def list_bigip_devices(ctx: Context = None) -> str:
    """
    List all configured BIG-IP devices from the configuration file.

    Returns:
        A formatted list of available BIG-IP devices with their details
    """
    if ctx:
        await ctx.info("Loading BIG-IP device configurations")

    try:
        devices = load_bigip_config()

        if not devices:
            return "No BIG-IP devices configured. Please add devices to bigip_config.json"

        output = [f"Found {len(devices)} configured BIG-IP device(s):\n"]

        for name, device in devices.items():
            output.append(f"\n**{name}**")
            output.append(f"  - IP Address: {device.ip_address}")
            output.append(f"  - Username: {device.username}")
            output.append(f"  - SSL Verification: {'enabled' if device.verify_ssl else 'disabled'}")
            if device.description:
                output.append(f"  - Description: {device.description}")

        output.append("\n**Usage:** Use device name with list_virtual_servers tool")
        output.append("Example: list_virtual_servers(device_name='prod-lb-01')")

        return "\n".join(output)

    except Exception as e:
        if ctx:
            await ctx.error(f"Failed to load devices: {str(e)}")
        return f"❌ Error loading devices: {str(e)}"


# ============================================================================
# RESOURCES
# ============================================================================

@mcp.resource("config://server")
def get_server_config() -> str:
    """Get server configuration information"""
    config = {
        "name": "BIG-IP MCP Server",
        "version": "1.0.0",
        "description": "MCP server for F5 BIG-IP management",
        "capabilities": [
            "List virtual servers",
            "Token-based authentication",
            "Credential caching"
        ]
    }
    return json.dumps(config, indent=2)


# ============================================================================
# PROMPTS
# ============================================================================

@mcp.prompt
def help_prompt() -> str:
    """Get help about available BIG-IP server capabilities"""
    return """
    This BIG-IP MCP server provides tools to manage F5 BIG-IP devices:

    **Available Tools:**
    - `list_virtual_servers`: Query all virtual servers from a BIG-IP device
      - Requires: IP address, username, and password
      - Caches authentication token for subsequent requests to the same device
      - Returns detailed status of each virtual server
      - Optional: verify_ssl parameter (default: False for self-signed certs)

    **Usage:**
    Ask Claude to "list virtual servers on my BIG-IP" and provide:
    - BIG-IP IP address or hostname
    - Username
    - Password

    **Security:**
    - Authentication tokens are cached per-device for efficiency
    - Tokens automatically expire after 19 minutes
    - SSL verification can be enabled for production environments
    """


# ============================================================================
# SERVER EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Run the server using stdio transport (default for MCP)
    mcp.run()
