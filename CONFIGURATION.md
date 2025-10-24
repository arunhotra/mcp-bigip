# BIG-IP Configuration Guide

## Quick Setup

1. **Copy the example configuration:**
   ```bash
   cp bigip_config.example.json bigip_config.json
   ```

2. **Edit `bigip_config.json` with your BIG-IP devices:**
   ```json
   {
     "devices": {
       "prod-lb-01": {
         "ip_address": "10.1.1.10",
         "username": "admin",
         "password": "your-secure-password",
         "verify_ssl": false,
         "description": "Production load balancer 1"
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

3. **Restart the MCP server** (if running) or restart Claude Desktop

## Configuration Fields

### Device Configuration

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `ip_address` | Yes | BIG-IP management IP or hostname | `"10.1.1.10"` or `"bigip.example.com"` |
| `username` | Yes | BIG-IP username with API access | `"admin"` |
| `password` | Yes | BIG-IP password | `"MySecurePassword123"` |
| `verify_ssl` | No | Verify SSL certificates (default: false) | `false` for self-signed, `true` for valid certs |
| `description` | No | Human-readable description | `"Production LB in datacenter 1"` |

## Device Names

- Use descriptive, consistent names for your devices
- Good examples: `prod-lb-01`, `dev-bigip`, `dc1-lb-primary`
- Avoid spaces or special characters
- These names are used when calling the `list_virtual_servers` tool

## Security Best Practices

1. **Never commit `bigip_config.json`** - It's already in `.gitignore`
2. **Use read-only accounts** when possible
3. **Set appropriate file permissions:**
   ```bash
   chmod 600 bigip_config.json
   ```
4. **Enable SSL verification** (`verify_ssl: true`) for production devices with valid certificates
5. **Consider using service accounts** with limited permissions instead of admin accounts

## Usage Examples

### List all configured devices:
```
Show me the configured BIG-IP devices
```

### List virtual servers from a specific device:
```
List virtual servers on prod-lb-01
```

Or:
```
Show me the virtual servers on the lab-bigip device
```

### Manage AS3:
```
Check AS3 status on prod-lb-01
Install AS3 on lab-bigip
Upgrade AS3 on prod-lb-01
```

## AS3 Requirements

### Account Permissions
- **Admin account required** - AS3 installation requires the `admin` user account (not just a user with administrator role)
- If your config uses a non-admin account, AS3 operations will fail with a permission error
- Consider creating a separate device entry in your config with admin credentials for AS3 management

### BIG-IP Version
- BIG-IP 14.0+ required for AS3 token-based authentication
- BIG-IP 14.1+ recommended for AS3 version 3.50.0 and later
- Tested with BIG-IP 13.x, 14.x, 15.x, 16.x, 17.x

### Network Access
- Outbound HTTPS access to `github.com` required for downloading AS3 RPM packages
- GitHub API access required for fetching latest release information
- If behind a firewall, ensure these domains are whitelisted

### Installation Notes
- AS3 installation typically takes 2-5 minutes
- The tool polls installation status every 5 seconds with a 5-minute timeout
- After installation, AS3 may take an additional 5-10 seconds to fully initialize
- For HA clusters, install on the active device first, then synchronize

## Troubleshooting

### "Configuration file not found"
- Ensure `bigip_config.json` exists in the same directory as `server.py`
- Copy from `bigip_config.example.json` if needed

### "Device 'xxx' not found in configuration"
- Check the device name matches exactly (case-sensitive)
- Use `list_bigip_devices` tool to see available devices
- Verify JSON syntax is correct

### "Invalid JSON in configuration file"
- Validate your JSON using a JSON validator
- Common issues: missing commas, trailing commas, unescaped quotes
- Each device entry except the last needs a trailing comma

### Authentication failures
- Verify credentials are correct in `bigip_config.json`
- Check network connectivity to the BIG-IP
- Ensure the user account has API access permissions

### AS3 installation failures

**"Permission denied. AS3 installation requires admin account"**
- The user in your config must be the `admin` account
- Regular users with administrator role will NOT work
- Create a separate device entry with admin credentials for AS3 operations

**"Failed to download AS3 RPM"**
- Verify outbound internet access to GitHub
- Check firewall rules allow HTTPS to `github.com`
- Temporarily try from a browser to confirm connectivity

**"AS3 installation timed out after 5 minutes"**
- BIG-IP may be slow or under load
- Check BIG-IP system resources (CPU, memory)
- Try again during off-peak hours
- Use BIG-IP GUI to check package management tasks

**"Installation completed but AS3 verification failed"**
- AS3 may still be initializing (wait 30 seconds and check again)
- Check BIG-IP logs: `/var/log/restjavad.0.log`
- Verify AS3 package installed via BIG-IP GUI: iApps > Package Management LX

## Advanced Configuration

### Multiple Environments

Organize devices by environment:

```json
{
  "devices": {
    "prod-lb-01": { "ip_address": "10.1.1.10", ... },
    "prod-lb-02": { "ip_address": "10.1.1.11", ... },
    "staging-lb": { "ip_address": "10.2.1.10", ... },
    "dev-lb": { "ip_address": "10.3.1.10", ... },
    "lab-bigip": { "ip_address": "192.168.1.100", ... }
  }
}
```

### Production vs Lab Settings

```json
{
  "devices": {
    "prod-bigip": {
      "ip_address": "bigip.prod.example.com",
      "username": "svc_mcp_readonly",
      "password": "secure-production-password",
      "verify_ssl": true,
      "description": "Production - requires SSL verification"
    },
    "lab-bigip": {
      "ip_address": "192.168.1.100",
      "username": "admin",
      "password": "admin",
      "verify_ssl": false,
      "description": "Lab - self-signed certificate"
    }
  }
}
```

## File Location

The configuration file must be in the same directory as `server.py`:
```
/Users/a.ganti/Documents/code/mcp-servers/big-ip/
├── server.py
├── bigip_config.json          ← Your actual config (gitignored)
└── bigip_config.example.json  ← Example template
```
