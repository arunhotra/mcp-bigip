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
import asyncio
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
    pool: Optional[str] = None
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
                # Extract pool name from pool reference (format: /Common/pool_name)
                pool_ref = item.get("pool", "")
                pool_name = pool_ref.split("/")[-1] if pool_ref else None

                vs = VirtualServer(
                    name=item.get("name", ""),
                    full_path=item.get("fullPath", ""),
                    destination=item.get("destination", ""),
                    pool=pool_name,
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
# AS3 MANAGEMENT HELPERS
# ============================================================================

async def get_latest_as3_release() -> Dict:
    """
    Fetch the latest AS3 release information from GitHub API.

    Returns:
        Dictionary with: version, rpm_url, rpm_filename, sha256

    Raises:
        Exception: If GitHub API request fails
    """
    github_api_url = "https://api.github.com/repos/F5Networks/f5-appsvcs-extension/releases/latest"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(github_api_url, timeout=30.0)
            response.raise_for_status()

            data = response.json()
            version = data.get("tag_name", "").replace("v", "")  # Remove 'v' prefix

            # Find the RPM asset
            rpm_asset = None
            sha256_asset = None

            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".rpm") and "f5-appsvcs" in name:
                    rpm_asset = asset
                elif name.endswith(".rpm.sha256"):
                    sha256_asset = asset

            if not rpm_asset:
                raise Exception("Could not find AS3 RPM in latest GitHub release")

            return {
                "version": version,
                "rpm_url": rpm_asset.get("browser_download_url"),
                "rpm_filename": rpm_asset.get("name"),
                "sha256_url": sha256_asset.get("browser_download_url") if sha256_asset else None
            }

        except httpx.HTTPStatusError as e:
            raise Exception(f"GitHub API request failed: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Failed to fetch latest AS3 release: {str(e)}")


async def check_as3_installed(
    ip_address: str,
    token: str,
    verify_ssl: bool = False
) -> Optional[str]:
    """
    Check if AS3 is installed on BIG-IP and return the version.

    Args:
        ip_address: BIG-IP management IP
        token: Authentication token
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Version string if installed, None if not installed

    Raises:
        Exception: If API call fails (other than 404)
    """
    url = f"https://{ip_address}/mgmt/shared/appsvcs/info"

    headers = {
        "X-F5-Auth-Token": token,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(verify=verify_ssl) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)

            if response.status_code == 404:
                return None  # AS3 not installed

            response.raise_for_status()
            data = response.json()

            # AS3 returns version in the response
            return data.get("version", "unknown")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise Exception(f"Failed to check AS3 status: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Error checking AS3 installation: {str(e)}")


async def download_as3_rpm(rpm_url: str, rpm_filename: str) -> bytes:
    """
    Download AS3 RPM from GitHub.

    Args:
        rpm_url: Download URL for the RPM
        rpm_filename: Filename for logging purposes

    Returns:
        RPM file content as bytes

    Raises:
        Exception: If download fails
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(rpm_url, timeout=300.0)  # 5 minute timeout for large file
            response.raise_for_status()

            return response.content

        except httpx.HTTPStatusError as e:
            raise Exception(f"Failed to download AS3 RPM: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Error downloading AS3 RPM from GitHub: {str(e)}")


async def upload_as3_rpm(
    ip_address: str,
    token: str,
    rpm_filename: str,
    rpm_content: bytes,
    verify_ssl: bool = False
) -> bool:
    """
    Upload AS3 RPM to BIG-IP.

    Args:
        ip_address: BIG-IP management IP
        token: Authentication token
        rpm_filename: Name of the RPM file
        rpm_content: RPM file content as bytes
        verify_ssl: Whether to verify SSL certificates

    Returns:
        True if upload successful

    Raises:
        Exception: If upload fails
    """
    url = f"https://{ip_address}/mgmt/shared/file-transfer/uploads/{rpm_filename}"

    headers = {
        "X-F5-Auth-Token": token,
        "Content-Type": "application/octet-stream",
        "Content-Range": f"0-{len(rpm_content)-1}/{len(rpm_content)}"
    }

    async with httpx.AsyncClient(verify=verify_ssl) as client:
        try:
            response = await client.post(
                url,
                content=rpm_content,
                headers=headers,
                timeout=300.0  # 5 minute timeout for large file upload
            )
            response.raise_for_status()

            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise Exception("Authentication failed. AS3 installation requires admin account privileges.")
            elif e.response.status_code == 403:
                raise Exception("Permission denied. AS3 installation requires admin account (not just administrator role).")
            raise Exception(f"Failed to upload AS3 RPM: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Error uploading AS3 RPM to BIG-IP: {str(e)}")


async def install_as3_package(
    ip_address: str,
    token: str,
    rpm_filename: str,
    verify_ssl: bool = False
) -> str:
    """
    Install AS3 package on BIG-IP and wait for completion.

    Args:
        ip_address: BIG-IP management IP
        token: Authentication token
        rpm_filename: Name of the uploaded RPM file
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Success message with installation status

    Raises:
        Exception: If installation fails or times out
    """
    url = f"https://{ip_address}/mgmt/shared/iapp/package-management-tasks"

    headers = {
        "X-F5-Auth-Token": token,
        "Content-Type": "application/json"
    }

    payload = {
        "operation": "INSTALL",
        "packageFilePath": f"/var/config/rest/downloads/{rpm_filename}"
    }

    async with httpx.AsyncClient(verify=verify_ssl) as client:
        try:
            # Start installation task
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()

            task_data = response.json()
            task_id = task_data.get("id")

            if not task_id:
                raise Exception("No task ID returned from installation request")

            # Poll for task completion (max 5 minutes)
            task_url = f"{url}/{task_id}"
            max_attempts = 60  # 5 minutes with 5-second intervals
            attempt = 0

            while attempt < max_attempts:
                await asyncio.sleep(5)  # Wait 5 seconds between checks

                status_response = await client.get(task_url, headers=headers, timeout=30.0)
                status_response.raise_for_status()

                status_data = status_response.json()
                status = status_data.get("status")

                if status == "FINISHED":
                    return "AS3 installation completed successfully"
                elif status == "FAILED":
                    error_msg = status_data.get("errorMessage", "Unknown error")
                    raise Exception(f"AS3 installation failed: {error_msg}")

                attempt += 1

            raise Exception("AS3 installation timed out after 5 minutes")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise Exception("Authentication failed. AS3 installation requires admin account privileges.")
            elif e.response.status_code == 403:
                raise Exception("Permission denied. AS3 installation requires admin account (not just administrator role).")
            raise Exception(f"Failed to install AS3 package: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise Exception(f"Error installing AS3 package: {str(e)}")


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

        # Format the response as a table
        if not virtual_servers:
            return "No virtual servers found on this BIG-IP device."

        # Helper function to parse destination into IP and Port
        def parse_destination(dest: str):
            """Parse destination format: /Common/10.1.1.100:80 or 10.1.1.100:80"""
            if not dest:
                return "N/A", "N/A"
            # Remove partition prefix if present
            dest_clean = dest.split("/")[-1]
            # Split IP and port
            if ":" in dest_clean:
                ip, port = dest_clean.rsplit(":", 1)
                return ip, port
            return dest_clean, "N/A"

        # Build table header
        output = [
            f"## Virtual Servers on {credentials.ip_address} ({len(virtual_servers)} total)\n",
            "| Status | Name | Destination IP | Port | Pool |",
            "|--------|------|----------------|------|------|"
        ]

        # Build table rows
        for vs in virtual_servers:
            # Status indicator
            if vs.availability_status == "available":
                status = "🟢"  # Green circle
            elif vs.availability_status == "offline":
                status = "🔴"  # Red circle
            elif vs.availability_status == "unknown":
                status = "⚪"  # White circle
            else:
                status = "🟡"  # Yellow circle for other states

            # Parse destination
            dest_ip, dest_port = parse_destination(vs.destination)

            # Pool name or "None"
            pool_name = vs.pool if vs.pool else "None"

            # Add row
            output.append(f"| {status} | {vs.name} | {dest_ip} | {dest_port} | {pool_name} |")

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


@mcp.tool
async def manage_as3(
    device_name: str,
    action: str = "check",
    auto_install: bool = False,
    ctx: Context = None
) -> str:
    """
    Check, install, or upgrade F5 AS3 (Application Services 3 Extension) on BIG-IP.

    Args:
        device_name: Name of the BIG-IP device from configuration file
        action: Action to perform - "check" (default), "install", or "upgrade"
        auto_install: Set to True to proceed with installation/upgrade (default: False)

    Returns:
        Status message with AS3 version information and installation results
    """
    if ctx:
        await ctx.info(f"Starting AS3 management for device: {device_name}")

    # Validate action parameter
    if action not in ["check", "install", "upgrade"]:
        return f"❌ Invalid action '{action}'. Must be 'check', 'install', or 'upgrade'."

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

    # Check current AS3 installation status
    if ctx:
        await ctx.info("Checking AS3 installation status")

    try:
        installed_version = await check_as3_installed(
            ip_address=credentials.ip_address,
            token=token_obj.token,
            verify_ssl=credentials.verify_ssl
        )

        if ctx:
            if installed_version:
                await ctx.info(f"AS3 version {installed_version} is currently installed")
            else:
                await ctx.info("AS3 is not currently installed")

    except Exception as e:
        if ctx:
            await ctx.error(f"Failed to check AS3 status: {str(e)}")
        return f"❌ Failed to check AS3 status: {str(e)}"

    # Fetch latest AS3 version from GitHub
    if ctx:
        await ctx.info("Fetching latest AS3 release information from GitHub")

    try:
        latest_release = await get_latest_as3_release()
        latest_version = latest_release["version"]

        if ctx:
            await ctx.info(f"Latest AS3 version available: {latest_version}")

    except Exception as e:
        if ctx:
            await ctx.error(f"Failed to fetch latest AS3 release: {str(e)}")
        return f"❌ Failed to fetch latest AS3 release: {str(e)}"

    # Handle "check" action
    if action == "check":
        output = [f"## AS3 Status on {device_name} ({credentials.ip_address})\n"]

        if installed_version:
            output.append(f"**Installed Version:** {installed_version}")
        else:
            output.append("**Installed Version:** Not installed")

        output.append(f"**Latest Available:** {latest_version}")

        # Determine recommendation
        if not installed_version:
            output.append("\n**Recommendation:** AS3 is not installed.")
            output.append(f"To install: `manage_as3(device_name='{device_name}', action='install', auto_install=True)`")
        elif installed_version != latest_version:
            output.append(f"\n**Recommendation:** Newer version available ({latest_version}).")
            output.append(f"To upgrade: `manage_as3(device_name='{device_name}', action='upgrade', auto_install=True)`")
        else:
            output.append("\n✅ **Status:** AS3 is up to date!")

        return "\n".join(output)

    # Handle "install" action
    if action == "install":
        if installed_version:
            return (f"ℹ️ AS3 version {installed_version} is already installed on {device_name}. "
                   f"Use action='upgrade' to update to version {latest_version}.")

        if not auto_install:
            return (f"⚠️ AS3 is not installed. Latest version: {latest_version}\n\n"
                   f"To proceed with installation, run:\n"
                   f"`manage_as3(device_name='{device_name}', action='install', auto_install=True)`\n\n"
                   f"**Note:** AS3 installation requires admin account privileges.")

        # Proceed with installation
        if ctx:
            await ctx.info(f"Starting AS3 {latest_version} installation")

        try:
            # Download RPM
            if ctx:
                await ctx.info(f"Downloading AS3 RPM from GitHub: {latest_release['rpm_filename']}")

            rpm_content = await download_as3_rpm(
                rpm_url=latest_release["rpm_url"],
                rpm_filename=latest_release["rpm_filename"]
            )

            if ctx:
                await ctx.info(f"Downloaded {len(rpm_content)} bytes")

            # Upload RPM to BIG-IP
            if ctx:
                await ctx.info(f"Uploading RPM to BIG-IP at {credentials.ip_address}")

            await upload_as3_rpm(
                ip_address=credentials.ip_address,
                token=token_obj.token,
                rpm_filename=latest_release["rpm_filename"],
                rpm_content=rpm_content,
                verify_ssl=credentials.verify_ssl
            )

            if ctx:
                await ctx.info("RPM upload completed successfully")

            # Install package
            if ctx:
                await ctx.info("Starting AS3 package installation (this may take a few minutes)")

            install_result = await install_as3_package(
                ip_address=credentials.ip_address,
                token=token_obj.token,
                rpm_filename=latest_release["rpm_filename"],
                verify_ssl=credentials.verify_ssl
            )

            if ctx:
                await ctx.info(install_result)

            # Verify installation
            if ctx:
                await ctx.info("Verifying AS3 installation")

            # Wait a moment for AS3 to fully initialize
            await asyncio.sleep(5)

            verified_version = await check_as3_installed(
                ip_address=credentials.ip_address,
                token=token_obj.token,
                verify_ssl=credentials.verify_ssl
            )

            if verified_version:
                return (f"✅ **AS3 Installation Successful!**\n\n"
                       f"Device: {device_name} ({credentials.ip_address})\n"
                       f"Installed Version: {verified_version}\n"
                       f"Status: AS3 is now ready to use")
            else:
                return (f"⚠️ Installation completed but AS3 verification failed. "
                       f"The package may still be initializing. Please wait a moment and check again.")

        except Exception as e:
            if ctx:
                await ctx.error(f"AS3 installation failed: {str(e)}")
            return f"❌ AS3 installation failed: {str(e)}"

    # Handle "upgrade" action
    if action == "upgrade":
        if not installed_version:
            return (f"ℹ️ AS3 is not currently installed on {device_name}. "
                   f"Use action='install' to install version {latest_version}.")

        if installed_version == latest_version:
            return f"✅ AS3 is already at the latest version ({latest_version}) on {device_name}."

        if not auto_install:
            return (f"⚠️ AS3 upgrade available: {installed_version} → {latest_version}\n\n"
                   f"To proceed with upgrade, run:\n"
                   f"`manage_as3(device_name='{device_name}', action='upgrade', auto_install=True)`\n\n"
                   f"**Note:** AS3 installation requires admin account privileges.")

        # Proceed with upgrade (same process as install)
        if ctx:
            await ctx.info(f"Starting AS3 upgrade from {installed_version} to {latest_version}")

        try:
            # Download RPM
            if ctx:
                await ctx.info(f"Downloading AS3 RPM from GitHub: {latest_release['rpm_filename']}")

            rpm_content = await download_as3_rpm(
                rpm_url=latest_release["rpm_url"],
                rpm_filename=latest_release["rpm_filename"]
            )

            if ctx:
                await ctx.info(f"Downloaded {len(rpm_content)} bytes")

            # Upload RPM to BIG-IP
            if ctx:
                await ctx.info(f"Uploading RPM to BIG-IP at {credentials.ip_address}")

            await upload_as3_rpm(
                ip_address=credentials.ip_address,
                token=token_obj.token,
                rpm_filename=latest_release["rpm_filename"],
                rpm_content=rpm_content,
                verify_ssl=credentials.verify_ssl
            )

            if ctx:
                await ctx.info("RPM upload completed successfully")

            # Install package
            if ctx:
                await ctx.info("Starting AS3 package upgrade (this may take a few minutes)")

            install_result = await install_as3_package(
                ip_address=credentials.ip_address,
                token=token_obj.token,
                rpm_filename=latest_release["rpm_filename"],
                verify_ssl=credentials.verify_ssl
            )

            if ctx:
                await ctx.info(install_result)

            # Verify installation
            if ctx:
                await ctx.info("Verifying AS3 upgrade")

            # Wait a moment for AS3 to fully initialize
            await asyncio.sleep(5)

            verified_version = await check_as3_installed(
                ip_address=credentials.ip_address,
                token=token_obj.token,
                verify_ssl=credentials.verify_ssl
            )

            if verified_version == latest_version:
                return (f"✅ **AS3 Upgrade Successful!**\n\n"
                       f"Device: {device_name} ({credentials.ip_address})\n"
                       f"Previous Version: {installed_version}\n"
                       f"New Version: {verified_version}\n"
                       f"Status: AS3 is now ready to use")
            else:
                return (f"⚠️ Upgrade completed but verification returned version {verified_version}. "
                       f"The package may still be initializing. Please wait a moment and check again.")

        except Exception as e:
            if ctx:
                await ctx.error(f"AS3 upgrade failed: {str(e)}")
            return f"❌ AS3 upgrade failed: {str(e)}"


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
