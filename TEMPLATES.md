# AS3 Application Templates

This document explains how to create and use AS3 application templates with the BIG-IP MCP Server.

## Overview

Templates allow you to define reusable AS3 declarations with variable placeholders. The MCP server substitutes these variables with actual values (IP addresses from phpIPAM, application names, etc.) and deploys the configured application to BIG-IP.

## Template Location

Templates are stored in the `templates/` directory at the root of this project:

```
/Users/a.ganti/Documents/code/mcp-servers/big-ip/
├── server.py
├── templates/
│   ├── marketing.json
│   ├── engineering.json (example for future)
│   └── finance.json (example for future)
└── README.md
```

## Variable Syntax

Variables use double curly braces: `{{VARIABLE_NAME}}`

### Supported Variable Types

All variables use simple string substitution. To maintain valid JSON syntax, variables must be properly quoted in the template.

1. **String variables** - Simple text substitution
   ```json
   "virtualAddresses": ["{{VIRTUAL_IP}}"]
   ```

2. **Numbered pool members** - Individual variables for each pool member
   ```json
   "serverAddresses": [
     "{{POOL_MEMBER_1}}",
     "{{POOL_MEMBER_2}}"
   ]
   ```
   The tool automatically creates numbered variables from the pool members list.

### Standard Variables

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `{{TENANT_NAME}}` | String | AS3 tenant name | `"Marketing"` |
| `{{APP_NAME}}` | String | Application name | `"marketing_app"` |
| `{{VIRTUAL_IP}}` | String | Virtual server IP | `"10.1.100.5"` |
| `{{POOL_MEMBER_1}}` | String | First pool member IP | `"192.168.10.10"` |
| `{{POOL_MEMBER_2}}` | String | Second pool member IP | `"192.168.10.11"` |
| `{{POOL_MEMBER_N}}` | String | Nth pool member IP | `"192.168.10.12"` |

## Example Template

Here's the `marketing.json` template:

```json
{
  "class": "AS3",
  "action": "deploy",
  "persist": true,
  "declaration": {
    "class": "ADC",
    "schemaVersion": "3.0.0",
    "{{TENANT_NAME}}": {
      "class": "Tenant",
      "{{APP_NAME}}": {
        "class": "Application",
        "service": {
          "class": "Service_HTTP",
          "virtualAddresses": [
            "{{VIRTUAL_IP}}"
          ],
          "pool": "web_pool"
        },
        "web_pool": {
          "class": "Pool",
          "monitors": [
            "http"
          ],
          "members": [
            {
              "servicePort": 80,
              "serverAddresses": [
                "{{POOL_MEMBER_1}}",
                "{{POOL_MEMBER_2}}"
              ]
            }
          ]
        }
      }
    }
  }
}
```

## Creating Custom Templates

### Step 1: Start with a Working AS3 Declaration

Get a working AS3 declaration from:
- F5 AS3 documentation: https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/userguide/examples.html
- Export from existing BIG-IP configuration
- BIG-IP AS3 schema reference

### Step 2: Identify Dynamic Values

Determine which values should be variables:
- IP addresses (virtual servers, pool members)
- Names (tenant, application, pool)
- Ports (if variable per deployment)

### Step 3: Replace with Variables

Replace dynamic values with `{{VARIABLE_NAME}}` placeholders:

**Before:**
```json
"Sample_Tenant": {
  "class": "Tenant",
  "MyApp": {
    "virtualAddresses": ["10.1.1.10"]
  }
}
```

**After:**
```json
"{{TENANT_NAME}}": {
  "class": "Tenant",
  "{{APP_NAME}}": {
    "virtualAddresses": ["{{VIRTUAL_IP}}"]
  }
}
```

### Step 4: Save Template

Save as `templates/{name}.json` where `{name}` matches your phpIPAM section name or use case.

### Step 5: Test Template

Use MCP resources to view your template:
```
Check template templates://marketing
```

Or list all templates:
```
Check resource templates://available
```

## Template Naming Convention

### Match phpIPAM Sections

For automatic template selection, name templates after phpIPAM sections:

- phpIPAM section: "marketing" → `templates/marketing.json`
- phpIPAM section: "engineering" → `templates/engineering.json`
- phpIPAM section: "finance" → `templates/finance.json`

### Custom Names

You can use any name and specify it explicitly when calling the create_as3_app tool with the template_name parameter.

## Advanced Templates

### HTTPS with SSL

```json
{
  "class": "AS3",
  "declaration": {
    "{{TENANT_NAME}}": {
      "{{APP_NAME}}": {
        "service": {
          "class": "Service_HTTPS",
          "virtualAddresses": ["{{VIRTUAL_IP}}"],
          "virtualPort": 443,
          "serverTLS": "{{APP_NAME}}_tls",
          "pool": "web_pool"
        },
        "{{APP_NAME}}_tls": {
          "class": "TLS_Server",
          "certificates": [{
            "certificate": "{{APP_NAME}}_cert"
          }]
        },
        "{{APP_NAME}}_cert": {
          "class": "Certificate",
          "certificate": "{{TLS_CERT}}",
          "privateKey": "{{TLS_KEY}}"
        }
      }
    }
  }
}
```

### Multiple Pools

```json
{
  "web_pool": {
    "class": "Pool",
    "members": [{
      "serverAddresses": [
        "{{WEB_POOL_MEMBER_1}}",
        "{{WEB_POOL_MEMBER_2}}"
      ]
    }]
  },
  "api_pool": {
    "class": "Pool",
    "members": [{
      "serverAddresses": [
        "{{API_POOL_MEMBER_1}}",
        "{{API_POOL_MEMBER_2}}"
      ]
    }]
  }
}
```

### Custom Health Monitors

```json
{
  "web_pool": {
    "class": "Pool",
    "monitors": [{
      "use": "custom_http_monitor"
    }]
  },
  "custom_http_monitor": {
    "class": "Monitor",
    "monitorType": "http",
    "interval": 10,
    "timeout": 31,
    "send": "GET /health HTTP/1.1\r\nHost: {{DOMAIN_NAME}}\r\n\r\n",
    "receive": "200 OK"
  }
}
```

## Variable Validation

The server validates:
1. **Required variables** - All {{VARIABLES}} must be provided
2. **IP address format** - Virtual IPs must be valid IPv4
3. **AS3 schema** - Basic structure validation

## Troubleshooting

### "Template not found"

**Error:** `Template 'xyz' not found. Available templates: marketing`

**Solution:**
- Check template file exists in `templates/` directory
- Verify filename matches (case-sensitive, no .json in template_name parameter)
- List available: check resource `templates://available`

### "Template has unreplaced variables"

**Error:** `Template has unreplaced variables: POOL_MEMBERS. Provided variables: VIRTUAL_IP, TENANT_NAME`

**Solution:** Ensure all required variables are provided to `create_as3_app()` tool

### "Declaration validation failed: Invalid IP address"

**Error:** `Invalid IP address '10.1.1.256' at declaration.Marketing.service.virtualAddresses`

**Solution:** Verify IP addresses are valid (octets 0-255)

### "Invalid JSON in template after substitution"

**Error:** Usually caused by incorrect variable syntax

**Solution:**
- Always include quotes around variables in JSON arrays
- Correct: `"serverAddresses": ["{{POOL_MEMBER_1}}", "{{POOL_MEMBER_2}}"]`
- Wrong: `"serverAddresses": [{{POOL_MEMBER_1}}, {{POOL_MEMBER_2}}]`
- Each variable must be properly quoted to maintain valid JSON syntax

## Best Practices

1. **Start Simple** - Begin with basic HTTP applications, add complexity incrementally
2. **Test Incrementally** - Preview before deploying (`auto_deploy=False`)
3. **Version Control** - Track template changes in git
4. **Document Variables** - Add comments (outside JSON) explaining each variable
5. **Validate AS3** - Use F5's AS3 schema validator before creating templates
6. **Reuse Patterns** - Copy working templates as starting points

## Resources

- **F5 AS3 Documentation**: https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/
- **AS3 Schema Reference**: https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/refguide/schema-reference.html
- **AS3 Examples**: https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/userguide/examples.html
- **MCP Resources**: Access via `templates://available` and `templates://{name}`
- **Workflow Guide**: Use MCP prompt `create_app_workflow()`
