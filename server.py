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
import re
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
# AS3 APPLICATION CREATION HELPERS
# ============================================================================

def load_as3_template(template_name: str) -> Dict:
    """
    Load AS3 template from templates directory.

    Args:
        template_name: Name of the template (without .json extension)

    Returns:
        Template as Python dictionary

    Raises:
        Exception: If template file not found or invalid JSON
    """
    template_path = Path(__file__).parent / "templates" / f"{template_name}.json"

    if not template_path.exists():
        # List available templates
        templates_dir = Path(__file__).parent / "templates"
        if templates_dir.exists():
            available = [f.stem for f in templates_dir.glob("*.json")]
            if available:
                raise Exception(
                    f"Template '{template_name}' not found. "
                    f"Available templates: {', '.join(available)}"
                )
        raise Exception(
            f"Template '{template_name}' not found. "
            f"No templates directory found at {templates_dir}"
        )

    try:
        with open(template_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON in template '{template_name}': {str(e)}")
    except Exception as e:
        raise Exception(f"Error loading template '{template_name}': {str(e)}")


def render_as3_template(template: Dict, variables: Dict) -> Dict:
    """
    Render AS3 template by replacing variable placeholders.

    Variable format: {{VARIABLE_NAME}}
    Special handling for arrays: {{POOL_MEMBERS}} expects a list and converts to JSON array

    Args:
        template: Template dictionary with {{VARIABLE}} placeholders
        variables: Dictionary of variable names to values

    Returns:
        Rendered template with all variables substituted

    Raises:
        Exception: If required variables are missing
    """
    # Convert template to JSON string for easy substitution
    template_str = json.dumps(template, indent=2)

    # Track which variables were found in template
    found_vars = set()

    # Replace each variable
    for var_name, var_value in variables.items():
        placeholder = f"{{{{{var_name}}}}}"

        if placeholder in template_str:
            found_vars.add(var_name)

            # Special handling for list/array variables
            if isinstance(var_value, list):
                # Convert list to JSON array string
                var_value_str = json.dumps(var_value)
            else:
                var_value_str = str(var_value)

            template_str = template_str.replace(placeholder, var_value_str)

    # Check for any remaining unreplaced variables
    import re
    remaining_vars = re.findall(r'\{\{([A-Z_]+)\}\}', template_str)
    if remaining_vars:
        raise Exception(
            f"Template has unreplaced variables: {', '.join(set(remaining_vars))}. "
            f"Provided variables: {', '.join(variables.keys())}"
        )

    # Convert back to dictionary
    try:
        return json.loads(template_str)
    except json.JSONDecodeError as e:
        raise Exception(f"Error rendering template (invalid JSON after substitution): {str(e)}")


def validate_as3_declaration(declaration: Dict) -> tuple[bool, str]:
    """
    Validate AS3 declaration structure and content.

    Args:
        declaration: AS3 declaration dictionary

    Returns:
        Tuple of (is_valid, error_message)
        If valid: (True, "")
        If invalid: (False, "error description")
    """
    # Check required top-level fields
    if "class" not in declaration or declaration["class"] != "AS3":
        return False, "Declaration must have 'class': 'AS3'"

    if "declaration" not in declaration:
        return False, "Declaration must have 'declaration' property"

    decl = declaration["declaration"]

    if "class" not in decl or decl["class"] != "ADC":
        return False, "Declaration.class must be 'ADC'"

    # Validate IP addresses in virtualAddresses
    import re
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')

    def validate_ip(ip_str):
        """Validate IP address format"""
        if not ip_pattern.match(ip_str):
            return False
        octets = ip_str.split('.')
        return all(0 <= int(octet) <= 255 for octet in octets)

    def check_virtual_addresses(obj, path=""):
        """Recursively find and validate virtualAddresses"""
        if isinstance(obj, dict):
            if "virtualAddresses" in obj:
                addrs = obj["virtualAddresses"]
                if not isinstance(addrs, list):
                    return False, f"virtualAddresses at {path} must be a list"
                for addr in addrs:
                    if not validate_ip(addr):
                        return False, f"Invalid IP address '{addr}' at {path}.virtualAddresses"

            for key, value in obj.items():
                is_valid, msg = check_virtual_addresses(value, f"{path}.{key}")
                if not is_valid:
                    return is_valid, msg

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                is_valid, msg = check_virtual_addresses(item, f"{path}[{i}]")
                if not is_valid:
                    return is_valid, msg

        return True, ""

    # Validate IPs in declaration
    is_valid, error_msg = check_virtual_addresses(decl)
    if not is_valid:
        return False, error_msg

    return True, ""


async def deploy_as3_declaration(
    ip_address: str,
    token: str,
    declaration: Dict,
    verify_ssl: bool = False
) -> str:
    """
    Deploy AS3 declaration to BIG-IP.

    Args:
        ip_address: BIG-IP management IP
        token: Authentication token
        declaration: AS3 declaration dictionary
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Success message with deployment details

    Raises:
        Exception: If deployment fails or times out
    """
    url = f"https://{ip_address}/mgmt/shared/appsvcs/declare"

    headers = {
        "X-F5-Auth-Token": token,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(verify=verify_ssl) as client:
        try:
            # Deploy declaration
            response = await client.post(
                url,
                json=declaration,
                headers=headers,
                timeout=60.0  # Initial POST timeout
            )
            response.raise_for_status()

            result = response.json()

            # AS3 returns immediate result or task ID
            # Check if deployment is synchronous or asynchronous
            if result.get("results"):
                # Synchronous response
                results = result["results"]
                # Check for errors in results
                for tenant_result in results:
                    if isinstance(tenant_result, dict):
                        if tenant_result.get("code") not in [200, 201]:
                            message = tenant_result.get("message", "Unknown error")
                            return f"AS3 deployment failed: {message}"

                return "AS3 declaration deployed successfully"

            # If we get a task ID, poll for completion
            task_id = result.get("id")
            if task_id:
                # Poll task endpoint
                task_url = f"https://{ip_address}/mgmt/shared/appsvcs/task/{task_id}"
                max_attempts = 120  # 10 minutes with 5-second intervals
                attempt = 0

                while attempt < max_attempts:
                    await asyncio.sleep(5)

                    status_response = await client.get(task_url, headers=headers, timeout=30.0)
                    status_response.raise_for_status()

                    status_data = status_response.json()

                    # Check if task is complete
                    results = status_data.get("results", [])
                    if results:
                        # Check for errors
                        for tenant_result in results:
                            if isinstance(tenant_result, dict):
                                code = tenant_result.get("code", 0)
                                if code not in [200, 201, 202]:
                                    message = tenant_result.get("message", "Unknown error")
                                    return f"AS3 deployment failed: {message}"

                        return "AS3 declaration deployed successfully"

                    attempt += 1

                raise Exception("AS3 deployment timed out after 10 minutes")

            # No task ID and no immediate results
            return "AS3 declaration submitted (status unknown)"

        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            try:
                error_json = json.loads(error_text)
                error_msg = error_json.get("message", error_text)
            except:
                error_msg = error_text

            raise Exception(f"AS3 deployment failed: {e.response.status_code} - {error_msg}")
        except Exception as e:
            raise Exception(f"Error deploying AS3 declaration: {str(e)}")


# ============================================================================
# PHPIPAM INTEGRATION HELPERS
# ============================================================================

async def reserve_vip_from_phpipam(subnet_id: str, hostname: str) -> str:
    """
    Reserve first available IP from phpIPAM subnet for virtual server.

    Note: This function assumes phpIPAM MCP server is available and will be called
    by Claude. It returns instructions for Claude to call the phpIPAM tool.

    Args:
        subnet_id: phpIPAM subnet ID
        hostname: Hostname for the IP reservation

    Returns:
        Instruction string for Claude to call phpIPAM

    Raises:
        Exception: This function should not be called directly - it's a placeholder
    """
    raise Exception(
        "This function is a placeholder. Claude should call the phpIPAM MCP server's "
        f"reserve_ip_address tool with subnet_id='{subnet_id}' and hostname='{hostname}'"
    )


async def get_reserved_ips_from_phpipam(subnet_id: str) -> Dict:
    """
    Get all reserved IP addresses from phpIPAM subnet.

    Note: This function assumes phpIPAM MCP server is available and will be called
    by Claude. It returns instructions for Claude to call the phpIPAM tool.

    Args:
        subnet_id: phpIPAM subnet ID

    Returns:
        Instruction string for Claude to call phpIPAM

    Raises:
        Exception: This function should not be called directly - it's a placeholder
    """
    raise Exception(
        "This function is a placeholder. Claude should call the phpIPAM MCP server's "
        f"get_subnet_details tool with subnet_id='{subnet_id}' and include_addresses=True"
    )


def parse_pool_selection(selection: str, available_ips: List[Dict]) -> List[str]:
    """
    Parse user's pool member selection from text input.

    Supports formats:
    - Numbers: "1 and 2", "1, 2", "1,2"
    - IPs: "172.16.100.10 and 172.16.100.11"
    - Hostnames: "web-mkt-01 and web-mkt-02"
    - Mixed: "1 and 172.16.100.11"

    Args:
        selection: User's selection text
        available_ips: List of available IP dictionaries from phpIPAM
                       Format: [{"ip": "172.16.100.10", "hostname": "web-mkt-01"}, ...]

    Returns:
        List of selected IP addresses

    Raises:
        Exception: If selection cannot be parsed or IPs not found
    """
    if not selection or not selection.strip():
        raise Exception("No pool member selection provided")

    selection = selection.lower().strip()
    selected_ips = []

    # Extract numbers (for numbered selections like "1 and 2")
    numbers = re.findall(r'\d+', selection)

    # Extract IP addresses
    ip_pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
    ips_in_selection = re.findall(ip_pattern, selection)

    # Build mapping of index -> IP and hostname -> IP
    index_to_ip = {}
    hostname_to_ip = {}
    all_ips = []

    for idx, ip_info in enumerate(available_ips, start=1):
        ip = ip_info.get('ip', '')
        hostname = ip_info.get('hostname', '').lower()

        index_to_ip[str(idx)] = ip
        if hostname:
            hostname_to_ip[hostname] = ip
        all_ips.append(ip)

    # Process numbers (highest priority)
    for num in numbers:
        if num in index_to_ip:
            ip = index_to_ip[num]
            if ip not in selected_ips:
                selected_ips.append(ip)

    # Process explicit IPs
    for ip in ips_in_selection:
        if ip in all_ips and ip not in selected_ips:
            selected_ips.append(ip)

    # Process hostnames (if no numbers or IPs matched)
    if not selected_ips:
        for hostname, ip in hostname_to_ip.items():
            if hostname in selection and ip not in selected_ips:
                selected_ips.append(ip)

    if not selected_ips:
        raise Exception(
            f"Could not parse selection '{selection}'. "
            f"Please provide numbers (e.g., '1 and 2'), "
            f"IPs (e.g., '172.16.100.10 and 172.16.100.11'), "
            f"or hostnames"
        )

    return selected_ips


def format_pool_selection_prompt(subnet_info: Dict, reserved_ips: List[Dict]) -> str:
    """
    Format the pool member selection prompt for user.

    Args:
        subnet_info: Subnet information dict
        reserved_ips: List of reserved IP dicts from phpIPAM

    Returns:
        Formatted string prompting user to select pool members
    """
    if not reserved_ips:
        return (
            f"❌ No reserved IP addresses found in subnet {subnet_info.get('subnet', 'unknown')}. "
            "Please reserve some IPs first using phpIPAM before creating the application."
        )

    output = [
        f"## Available Web Servers\n",
        f"**Subnet:** {subnet_info.get('subnet', 'unknown')}/{subnet_info.get('mask', '?')}",
        f"**Description:** {subnet_info.get('description', 'N/A')}\n",
        f"Found {len(reserved_ips)} reserved IP(s):\n"
    ]

    for idx, ip_info in enumerate(reserved_ips, start=1):
        ip = ip_info.get('ip', 'unknown')
        hostname = ip_info.get('hostname', 'N/A')
        description = ip_info.get('description', '')

        line = f"{idx}. **{ip}** - {hostname}"
        if description:
            line += f" ({description[:50]})"

        output.append(line)

    output.append("\n**Next Step:** Please specify which servers to include in the pool.")
    output.append("Examples:")
    output.append("- By number: `Use 1 and 2`")
    output.append("- By IP: `Use 172.16.100.10 and 172.16.100.11`")
    output.append("- By hostname: `Use web-mkt-01 and web-mkt-02`")

    return "\n".join(output)


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


@mcp.tool
async def create_as3_app(
    device_name: str,
    section_name: str,
    vip_subnet_id: str,
    pool_subnet_id: str,
    pool_member_selection: str = None,
    virtual_ip: str = None,
    pool_members: List[str] = None,
    app_name: str = None,
    template_name: str = None,
    auto_deploy: bool = False,
    ctx: Context = None
) -> str:
    """
    Create AS3 application with IP allocation from phpIPAM.

    This tool demonstrates cross-MCP-server integration with phpIPAM MCP server.

    Two usage modes:

    Mode 1: Direct deployment (when IPs are already known)
        - Provide virtual_ip and pool_members directly
        - Set auto_deploy=True to deploy immediately

    Mode 2: Guided workflow (Claude orchestrates phpIPAM calls)
        - Claude calls phpIPAM to reserve VIP and get pool options
        - User selects pool members
        - Claude calls this tool with results

    Args:
        device_name: BIG-IP device from config file (e.g., 'lab-bigip')
        section_name: phpIPAM section name (e.g., 'marketing')
        vip_subnet_id: phpIPAM subnet ID for virtual server IP (e.g., '8')
        pool_subnet_id: phpIPAM subnet ID for pool member IPs (e.g., '7')
        pool_member_selection: User's selection of pool members (e.g., '1 and 2', '172.16.100.3 and 172.16.100.4')
                              Leave empty for guided mode
        virtual_ip: Virtual server IP address (optional, for direct deployment)
        pool_members: List of pool member IPs (optional, for direct deployment)
        app_name: Application name (optional, defaults to '{section_name}_app')
        template_name: Template to use (optional, defaults to section_name)
        auto_deploy: Set to True to deploy without preview (default: False)

    Returns:
        - Pool selection prompt (guided mode without pool_member_selection)
        - Preview (if pool_member_selection provided or direct mode, auto_deploy=False)
        - Deployment status (if auto_deploy=True)

    Example - Direct deployment:
        create_as3_app(
            device_name='lab-bigip',
            section_name='marketing',
            vip_subnet_id='8',
            pool_subnet_id='7',
            virtual_ip='192.168.50.3',
            pool_members=['172.16.100.3', '172.16.100.4'],
            auto_deploy=True
        )
    """
    state_key = f"as3_app_{section_name}"

    if ctx:
        await ctx.info(f"AS3 app creation for section: {section_name}")

    # Determine mode: Direct (IPs provided) or Guided (orchestrated via Claude)
    if virtual_ip and pool_members:
        # Mode 1: Direct deployment with provided IPs
        if ctx:
            await ctx.info(f"Direct deployment mode - VIP: {virtual_ip}, Pool: {pool_members}")
        selected_ips = pool_members
    else:
        # Mode 2: Guided workflow with phpIPAM orchestration
        # Step 1: Handle VIP reservation (auto or from cache)
        app_state = ctx.get_state(state_key) if ctx else None

        if app_state and app_state.get("virtual_ip"):
            virtual_ip = app_state["virtual_ip"]
            if ctx:
                await ctx.info(f"Using cached VIP: {virtual_ip}")
        else:
            # Need to tell Claude to call phpIPAM to reserve VIP
            return f"""## Step 1: Reserve Virtual IP

To proceed, please use the phpIPAM MCP server to reserve a virtual IP:

**Action needed:**
Call phpIPAM's `reserve_ip_address` tool with:
- `subnet_id`: `{vip_subnet_id}`
- `hostname`: `{section_name}-vip`

Once you have the reserved IP, call this tool again with the same parameters.

**Note:** I'll cache the VIP for subsequent calls."""

        # Step 2: Handle pool member selection
        if not pool_member_selection:
            # Need to tell Claude to get subnet details from phpIPAM
            return f"""## Step 2: Show Pool Member Options

**Virtual IP Reserved:** {virtual_ip} ✓

To see available pool members, please use the phpIPAM MCP server:

**Action needed:**
Call phpIPAM's `get_subnet_details` tool with:
- `subnet_id`: `{pool_subnet_id}`
- `include_addresses`: `True`

This will show all reserved IPs in the web servers subnet. Then specify which servers to use.

**Example selections:**
- By number: "1 and 2"
- By IP: "172.16.100.10 and 172.16.100.11"
- By hostname: "web-mkt-01 and web-mkt-02"
"""

        # Step 3: Parse pool selection (guided mode)
        # This requires Claude to have already shown the user the list
        # For now, we'll parse the selection text
        try:
            # Extract IPs from selection (support "1 and 2" format or IP format)
            # Simple parsing: look for IP addresses in the selection
            ip_pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
            selected_ips = re.findall(ip_pattern, pool_member_selection)

            if not selected_ips:
                # If no IPs found, assume user provided description like "1 and 2"
                # We need the actual IPs from phpIPAM context
                return f"""❌ Could not parse IP addresses from selection: '{pool_member_selection}'

Please provide the actual IP addresses of the pool members you want to use.

**Example:** "172.16.100.10 and 172.16.100.11"

Or first show the available servers using phpIPAM's `get_subnet_details` tool."""

            if len(selected_ips) < 2:
                return f"❌ Please select at least 2 pool members. Found only: {selected_ips}"

            selected_ips = selected_ips[:2]  # Use first 2 IPs

        except Exception as e:
            return f"❌ Error parsing pool selection: {str(e)}"

    # Step 4: Load device config and authenticate
    try:
        device = get_device_by_name(device_name)
        if ctx:
            await ctx.info(f"Loaded BIG-IP config: {device_name}")
    except Exception as e:
        return f"❌ Configuration error: {str(e)}"

    credentials = BIGIPCredentials(
        ip_address=device.ip_address,
        username=device.username,
        password=device.password,
        verify_ssl=device.verify_ssl
    )

    # Check for cached token
    cached_token = ctx.get_state(f"bigip_token_{device_name}") if ctx else None
    token_obj = None

    if cached_token:
        token_obj = AuthToken(**cached_token)
        if token_obj.expires_at <= datetime.now():
            token_obj = None

    if not token_obj:
        try:
            token_obj = await authenticate_bigip(credentials)
            if ctx:
                ctx.set_state(f"bigip_token_{device_name}", token_obj.model_dump())
        except Exception as e:
            return f"❌ Authentication failed: {str(e)}"

    # Step 5: Load and render template
    template_to_use = template_name if template_name else section_name

    try:
        template = load_as3_template(template_to_use)
    except Exception as e:
        return f"❌ Failed to load template: {str(e)}"

    app_name_final = app_name if app_name else f"{section_name}_app"
    variables = {
        "TENANT_NAME": section_name.title(),
        "APP_NAME": app_name_final,
        "VIRTUAL_IP": virtual_ip,
    }

    # Add individual pool member variables
    for i, member_ip in enumerate(selected_ips, start=1):
        variables[f"POOL_MEMBER_{i}"] = member_ip

    try:
        declaration = render_as3_template(template, variables)
    except Exception as e:
        return f"❌ Failed to render template: {str(e)}"

    # Validate declaration
    is_valid, error_msg = validate_as3_declaration(declaration)
    if not is_valid:
        return f"❌ Declaration validation failed: {error_msg}"

    # Step 6: Preview or deploy
    if not auto_deploy:
        pool_members_str = "\n  - ".join([f"{ip}:80" for ip in selected_ips])

        preview = f"""## AS3 Application Preview

**Device:** {device_name} ({credentials.ip_address})
**Tenant:** {variables['TENANT_NAME']}
**Application:** {variables['APP_NAME']}

### Configuration:
- **Virtual Server IP:** {virtual_ip}:80
- **Pool Members:**
  - {pool_members_str}
- **Load Balancing:** Round-robin
- **Health Monitor:** HTTP

### Template: {template_to_use}

**To deploy:** Call this tool again with `auto_deploy=True`
"""
        return preview

    # Deploy
    if ctx:
        await ctx.info("Deploying AS3 declaration")

    try:
        result = await deploy_as3_declaration(
            ip_address=credentials.ip_address,
            token=token_obj.token,
            declaration=declaration,
            verify_ssl=credentials.verify_ssl
        )

        # Clear cached state after successful deployment
        if ctx:
            ctx.set_state(state_key, None)

        pool_members_str = ", ".join(selected_ips)
        return f"""✅ **AS3 Application Deployed Successfully!**

**Device:** {device_name} ({credentials.ip_address})
**Tenant:** {variables['TENANT_NAME']}
**Application:** {variables['APP_NAME']}

### Configuration:
- **Virtual Server:** {virtual_ip}:80
- **Pool Members:** {pool_members_str}
- **Status:** Active and ready to receive traffic

The application is now live and will distribute traffic across the pool members.
"""

    except Exception as e:
        return f"❌ Deployment failed: {str(e)}"


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


@mcp.resource("templates://available")
def list_available_templates() -> str:
    """List all available AS3 application templates"""
    templates_dir = Path(__file__).parent / "templates"

    if not templates_dir.exists():
        return json.dumps({
            "templates": [],
            "message": "No templates directory found"
        }, indent=2)

    template_files = list(templates_dir.glob("*.json"))

    templates = []
    for template_file in template_files:
        template_name = template_file.stem
        try:
            with open(template_file, 'r') as f:
                template_data = json.load(f)

            # Extract variables from template
            template_str = json.dumps(template_data)
            variables = re.findall(r'\{\{([A-Z_]+)\}\}', template_str)
            unique_vars = list(set(variables))

            templates.append({
                "name": template_name,
                "file": template_file.name,
                "variables": unique_vars,
                "description": f"AS3 template for {template_name} applications"
            })
        except Exception as e:
            templates.append({
                "name": template_name,
                "file": template_file.name,
                "error": f"Failed to load: {str(e)}"
            })

    result = {
        "count": len(templates),
        "templates": templates
    }

    return json.dumps(result, indent=2)


@mcp.resource("templates://{template_name}")
def get_template_content(template_name: str) -> str:
    """Get the content of a specific AS3 template"""
    try:
        template = load_as3_template(template_name)

        # Extract variables
        template_str = json.dumps(template)
        variables = re.findall(r'\{\{([A-Z_]+)\}\}', template_str)
        unique_vars = list(set(variables))

        result = {
            "name": template_name,
            "variables": unique_vars,
            "template": template
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


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


@mcp.prompt
def create_app_workflow() -> str:
    """Guide for creating AS3 applications with phpIPAM integration"""
    return """
    # AS3 Application Creation Workflow

    This workflow demonstrates cross-MCP-server integration between phpIPAM and BIG-IP servers.

    ## Prerequisites
    - Both phpIPAM and BIG-IP MCP servers must be connected to Claude Desktop
    - AS3 must be installed on the BIG-IP device
    - phpIPAM must be configured with sections and subnets

    ## Step-by-Step Process

    ### 1. List Available Sections (phpIPAM)
    Ask Claude: "List all sections from phpIPAM"
    - This uses the phpIPAM server's `list_sections()` tool
    - Returns: Section IDs, names, and descriptions

    ### 2. Select Your Section
    Choose the section for your application (e.g., "marketing", "engineering")

    ### 3. Reserve Virtual IP (phpIPAM)
    The workflow will:
    - Find the appropriate subnet for virtual servers in your section
    - Reserve the first available IP for your virtual server
    - Tool: `reserve_ip_address(subnet_id, hostname)`

    ### 4. Get Pool Member IPs (phpIPAM)
    Ask Claude: "Show me web servers in the marketing section"
    - Tool: `search_subnets(query="marketing web")`
    - Tool: `get_subnet_details(subnet_id, include_addresses=true)`
    - Select 2 or more IPs for your pool members

    ### 5. Create Application (BIG-IP)
    Ask Claude: "Create AS3 application for marketing using these IPs"
    - Tool: `create_as3_app(device_name, section_name, virtual_ip, pool_members)`
    - Claude will generate AS3 declaration from template
    - Preview declaration before deployment
    - Confirm deployment

    ## Example Interaction

    ```
    User: "I want to create a load balancer for the marketing department"

    Claude: [Calls phpIPAM list_sections()]
           "Found these sections: marketing, engineering, finance"

    User: "Use marketing"

    Claude: [Reserves VIP] "Reserved 10.1.100.5 for virtual server"
           [Lists web servers] "Found: 192.168.10.10, 192.168.10.11, 192.168.10.12"

    User: "Use the first two"

    Claude: [Shows preview] "Will create:
             VIP: 10.1.100.5
             Pool: 192.168.10.10, 192.168.10.11
             Deploy to lab-bigip?"

    User: "Yes"

    Claude: [Deploys] "✅ Application created successfully!"
    ```

    ## MCP Features Demonstrated

    - **Cross-Server Orchestration**: Claude coordinates between two MCP servers
    - **Resources**: View available templates via `templates://available`
    - **Prompts**: This workflow guide
    - **Context State**: Cached authentication tokens
    - **Human-in-the-Loop**: Preview before deployment
    """


# ============================================================================
# SERVER EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Run the server using stdio transport (default for MCP)
    mcp.run()
