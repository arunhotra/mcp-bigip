# MCP Features Guide

**Purpose:** Learn how Model Context Protocol (MCP) features work through this BIG-IP server implementation.

This guide is designed for developers learning MCP. Each section explains a feature, shows the code, and demonstrates how it works in practice.

---

## Table of Contents

1. [What is MCP?](#what-is-mcp)
2. [Feature 1: Tools](#feature-1-tools) (You already know this)
3. [Feature 2: Resources](#feature-2-resources) ⭐ NEW
4. [Feature 3: Prompts](#feature-3-prompts) ⭐ NEW
5. [Feature 4: Context State](#feature-4-context-state) ⭐ NEW
6. [Feature 5: Cross-Server Integration](#feature-5-cross-server-integration) ⭐ NEW
7. [Complete Workflow Diagram](#complete-workflow-diagram)
8. [Code Location Reference](#code-location-reference)
9. [Learning Path](#learning-path)

---

## What is MCP?

**Model Context Protocol (MCP)** is a standardized way for AI assistants (like Claude) to interact with external systems. Think of it as an API specifically designed for AI.

### Core Concept

```
┌─────────────┐         MCP Protocol        ┌──────────────────┐
│             │ ◄────────────────────────► │                  │
│   Claude    │    (JSON-RPC over stdio)    │   MCP Server     │
│  (AI Agent) │                             │  (Your Code)     │
│             │ ◄────────────────────────► │                  │
└─────────────┘                             └──────────────────┘
                                                      │
                                                      │ Connects to
                                                      ▼
                                            ┌──────────────────┐
                                            │   BIG-IP Device  │
                                            │   (Target System)│
                                            └──────────────────┘
```

### Why MCP?

- **Standardized**: One protocol for all integrations
- **Secure**: Credentials stay in your MCP server, not with Claude
- **Composable**: Multiple MCP servers work together
- **Stateful**: Session-based interactions with caching

---

## Feature 1: Tools

**What:** Functions that Claude can call to perform actions.

**When to use:** Any operation that changes state or retrieves dynamic data.

### Example from our codebase

```python
@mcp.tool
async def list_virtual_servers(
    device_name: str,
    ctx: Context = None
) -> str:
    """List all virtual servers from a BIG-IP device"""
    # Implementation...
```

**Location in code:** `server.py:937-1067`

### How Claude uses it:

**User:** "Show me virtual servers on lab-bigip"

**Claude calls:**
```python
list_virtual_servers(device_name="lab-bigip")
```

**Result:** Returns formatted table of virtual servers

### All Tools in This Server

| Tool Name | Purpose | Line |
|-----------|---------|------|
| `list_virtual_servers` | Query BIG-IP virtual servers | 937 |
| `list_bigip_devices` | Show configured devices | 1069 |
| `manage_as3` | Install/upgrade AS3 | 1107 |
| `create_as3_app` | Deploy AS3 applications | 1417 |

---

## Feature 2: Resources

**What:** Static or semi-static data that Claude can read (like files in a filesystem).

**When to use:** Configuration data, templates, catalogs, documentation.

**Key difference from Tools:** Resources are **read-only data access**, Tools are **actions**.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Resource URIs                             │
├─────────────────────────────────────────────────────────────┤
│  config://server              ─►  Server metadata           │
│  templates://available        ─►  List of all templates     │
│  templates://marketing        ─►  Specific template content │
│  templates://engineering      ─►  Specific template content │
└─────────────────────────────────────────────────────────────┘
          │
          │ Claude reads these like files
          ▼
┌─────────────────────────────────────────────────────────────┐
│  "Show me available templates"                               │
│  "What variables does the marketing template use?"           │
│  "Let me see the server configuration"                       │
└─────────────────────────────────────────────────────────────┘
```

### Resource 1: Server Configuration

**URI:** `config://server`

**Purpose:** Server metadata and capabilities

**Code:** `server.py:1684-1697`

```python
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
```

**How to use:**
```
User: "What can this BIG-IP server do?"
Claude: [Reads config://server resource]
        "This server can list virtual servers, uses token authentication, and caches credentials..."
```

### Resource 2: Template Catalog

**URI:** `templates://available`

**Purpose:** List all AS3 templates with their variables

**Code:** `server.py:1700-1743`

```python
@mcp.resource("templates://available")
def list_available_templates() -> str:
    """List all available AS3 application templates"""
    templates_dir = Path(__file__).parent / "templates"

    # Scan directory for .json files
    template_files = list(templates_dir.glob("*.json"))

    templates = []
    for template_file in template_files:
        # Extract variables like {{VIRTUAL_IP}}, {{POOL_MEMBER_1}}
        variables = re.findall(r'\{\{([A-Z_]+)\}\}', template_str)

        templates.append({
            "name": template_name,
            "file": template_file.name,
            "variables": unique_vars,
            "description": f"AS3 template for {template_name} applications"
        })

    return json.dumps({"count": len(templates), "templates": templates}, indent=2)
```

**Example output:**
```json
{
  "count": 1,
  "templates": [
    {
      "name": "marketing",
      "file": "marketing.json",
      "variables": ["TENANT_NAME", "APP_NAME", "VIRTUAL_IP", "POOL_MEMBER_1", "POOL_MEMBER_2"],
      "description": "AS3 template for marketing applications"
    }
  ]
}
```

**How to use:**
```
User: "What templates are available?"
Claude: [Reads templates://available]
        "I found 1 template:
         - marketing: Requires TENANT_NAME, APP_NAME, VIRTUAL_IP, POOL_MEMBER_1, POOL_MEMBER_2"
```

### Resource 3: Specific Template Content

**URI Pattern:** `templates://{template_name}`

**Purpose:** Get the full content of a specific template

**Code:** `server.py:1746-1768`

```python
@mcp.resource("templates://{template_name}")
def get_template_content(template_name: str) -> str:
    """Get the content of a specific AS3 template"""
    template = load_as3_template(template_name)

    # Extract variables from template
    template_str = json.dumps(template)
    variables = re.findall(r'\{\{([A-Z_]+)\}\}', template_str)

    result = {
        "name": template_name,
        "variables": list(set(variables)),
        "template": template  # Full JSON template
    }

    return json.dumps(result, indent=2)
```

**How to use:**
```
User: "Show me the marketing template"
Claude: [Reads templates://marketing]
        "Here's the marketing template. It creates an HTTP virtual server with a pool..."
        [Shows full template JSON]
```

### Resources vs Tools: When to Use Each

| Scenario | Use Resource | Use Tool |
|----------|--------------|----------|
| List available templates | ✅ `templates://available` | ❌ |
| View template content | ✅ `templates://marketing` | ❌ |
| Deploy AS3 app | ❌ | ✅ `create_as3_app` tool |
| Server capabilities | ✅ `config://server` | ❌ |
| List virtual servers | ❌ | ✅ `list_virtual_servers` tool |
| Check AS3 status | ❌ | ✅ `manage_as3` tool |

**Rule of thumb:**
- **Resource** = "Show me what exists" (read-only catalog)
- **Tool** = "Do something" (action or dynamic query)

---

## Feature 3: Prompts

**What:** Pre-written guidance that Claude can load for contextual help.

**When to use:** Complex workflows, onboarding, multi-step processes.

**Think of it as:** Built-in documentation that Claude can reference to help users.

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Prompt System                              │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  User asks: "How do I create an AS3 app?"                    │
│                      │                                        │
│                      ▼                                        │
│  Claude loads: create_app_workflow prompt                    │
│                      │                                        │
│                      ▼                                        │
│  Claude reads comprehensive workflow guide                   │
│    - Step-by-step instructions                               │
│    - Example interaction                                     │
│    - Prerequisites                                           │
│    - MCP features explained                                  │
│                      │                                        │
│                      ▼                                        │
│  Claude guides user through workflow                         │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Prompt 1: Help Prompt

**Name:** `help_prompt`

**Purpose:** General server capabilities and usage

**Code:** `server.py:1775-1798`

```python
@mcp.prompt
def help_prompt() -> str:
    """Get help about available BIG-IP server capabilities"""
    return """
    This BIG-IP MCP server provides tools to manage F5 BIG-IP devices:

    **Available Tools:**
    - `list_virtual_servers`: Query all virtual servers from a BIG-IP device
      - Requires: IP address, username, and password
      - Caches authentication token for subsequent requests
      - Returns detailed status of each virtual server

    **Usage:**
    Ask Claude to "list virtual servers on my BIG-IP" and provide:
    - BIG-IP IP address or hostname
    - Username
    - Password

    **Security:**
    - Authentication tokens are cached per-device
    - Tokens automatically expire after 19 minutes
    - SSL verification can be enabled for production
    """
```

**How Claude uses it:**
```
User: "How do I use this BIG-IP server?"
Claude: [Loads help_prompt]
        "This server provides tools to manage F5 BIG-IP devices.
         You can list virtual servers by providing IP, username, and password.
         Authentication tokens are cached..."
```

### Prompt 2: Workflow Guide

**Name:** `create_app_workflow`

**Purpose:** Complete guide for AS3 application creation with cross-MCP integration

**Code:** `server.py:1801-1875`

```python
@mcp.prompt
def create_app_workflow() -> str:
    """Guide for creating AS3 applications with phpIPAM integration"""
    return """
    # AS3 Application Creation Workflow

    This workflow demonstrates cross-MCP-server integration.

    ## Prerequisites
    - Both phpIPAM and BIG-IP MCP servers connected
    - AS3 installed on BIG-IP
    - phpIPAM configured with sections/subnets

    ## Step-by-Step Process

    ### 1. List Available Sections (phpIPAM)
    Ask Claude: "List all sections from phpIPAM"

    ### 2. Select Your Section
    Choose section (e.g., "marketing", "engineering")

    ### 3. Reserve Virtual IP (phpIPAM)
    Workflow will reserve first available IP

    ### 4. Get Pool Member IPs (phpIPAM)
    Ask Claude: "Show me web servers in marketing"

    ### 5. Create Application (BIG-IP)
    Claude generates AS3 declaration and deploys

    ## Example Interaction
    [Full conversation example with tool calls]

    ## MCP Features Demonstrated
    - Cross-Server Orchestration
    - Resources (templates)
    - Prompts (this guide)
    - Context State (cached tokens)
    - Human-in-the-Loop
    """
```

**How Claude uses it:**
```
User: "I want to create a load balancer application"
Claude: [Loads create_app_workflow prompt]
        "Let me guide you through the AS3 application creation workflow.
         First, we need to list available sections from phpIPAM..."
        [Follows step-by-step guide]
```

### Why Prompts Are Powerful

**Without prompts:**
```
User: "Help me create an AS3 app"
Claude: "I can help with that. What device do you want to use?"
        [Generic conversation, Claude has to figure it out]
```

**With prompts:**
```
User: "Help me create an AS3 app"
Claude: [Loads create_app_workflow]
        "I'll guide you through the workflow. This involves:
         1. Selecting a section from phpIPAM
         2. Reserving a virtual IP
         3. Choosing pool members
         4. Deploying the AS3 configuration

         Let's start - let me list your available sections..."
        [Structured, consistent experience]
```

### Prompts vs Documentation Files

| Feature | Prompt | README.md |
|---------|--------|-----------|
| Claude can load automatically | ✅ | ❌ |
| Contextual guidance | ✅ | Limited |
| Always up-to-date | ✅ | Requires maintenance |
| Searchable by Claude | ✅ | ❌ |
| Human-readable | ✅ | ✅ |

**Best practice:** Use **both**
- Prompts for Claude's guidance
- Markdown docs for human reference

---

## Feature 4: Context State

**What:** Session-based caching that persists across multiple tool calls.

**When to use:** Authentication tokens, user selections, workflow state.

**Key benefit:** Avoid re-authenticating or re-querying data within the same session.

### Context State Operations

```python
from fastmcp import Context

# SET state
ctx.set_state(key: str, value: dict)

# GET state
cached_data = ctx.get_state(key: str) -> dict | None

# State persists for the entire conversation session
```

### Use Case 1: Authentication Token Caching

**Problem:** Re-authenticating to BIG-IP on every tool call is slow and wasteful.

**Solution:** Cache tokens with expiration tracking.

#### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│              Token Caching with Context State                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  First Call: list_virtual_servers(device="lab-bigip")          │
│       │                                                          │
│       ├─► Check: ctx.get_state("bigip_token_lab-bigip")        │
│       │          Result: None (no cached token)                 │
│       │                                                          │
│       ├─► Authenticate to BIG-IP                                │
│       │   POST /mgmt/shared/authn/login                        │
│       │   Response: { token: "XYSABC...", timeout: 1200 }      │
│       │                                                          │
│       ├─► Cache token:                                          │
│       │   ctx.set_state("bigip_token_lab-bigip", {             │
│       │     "token": "XYSABC...",                              │
│       │     "expires_at": "2025-10-24T10:30:00"                │
│       │   })                                                    │
│       │                                                          │
│       └─► Query virtual servers using token                     │
│                                                                  │
│  ═════════════════════════════════════════════════════════════  │
│                                                                  │
│  Second Call: manage_as3(device="lab-bigip", action="status")  │
│       │                                                          │
│       ├─► Check: ctx.get_state("bigip_token_lab-bigip")        │
│       │          Result: Found! { token: "XYSABC...",           │
│       │                          expires_at: "2025-10-24T10:30" }│
│       │                                                          │
│       ├─► Check expiration: Still valid ✓                       │
│       │                                                          │
│       ├─► Reuse cached token (no re-authentication!)            │
│       │                                                          │
│       └─► Check AS3 status using cached token                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Code Implementation

**Setting state:** `server.py:997`
```python
# After successful authentication
token_obj = await authenticate_bigip(credentials)

# Cache token with device-specific key
ctx.set_state(f"bigip_token_{device_name}", token_obj.model_dump())
await ctx.info("Successfully authenticated to BIG-IP")
```

**Getting state:** `server.py:974`
```python
# Check for cached token
cached_token = ctx.get_state(f"bigip_token_{device_name}")

if cached_token:
    token_obj = AuthToken(**cached_token)

    # Check if expired
    if token_obj.expires_at <= datetime.now():
        token_obj = None  # Expired, need to re-auth
        await ctx.info("Cached token expired, will re-authenticate")
    else:
        await ctx.info("Using cached authentication token")
```

#### Token Structure

```python
class AuthToken(BaseModel):
    token: str              # "XYSABC123..."
    expires_at: datetime    # "2025-10-24T10:30:00"
```

**State key pattern:** `bigip_token_{device_name}`
- `bigip_token_lab-bigip`
- `bigip_token_prod-lb-01`
- `bigip_token_bos-dmz-lb-01`

### Use Case 2: VIP Reservation Caching

**Problem:** In guided workflow, user reserves a VIP, then later needs to select pool members. The VIP needs to be remembered.

**Solution:** Cache the reserved VIP in context state.

#### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│           VIP Caching in Multi-Step Workflow                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Reserve VIP                                            │
│    User: "Create marketing app"                                 │
│    Claude → phpIPAM: reserve_ip_address(subnet_id=8)           │
│    Result: "192.168.50.3"                                       │
│         │                                                        │
│         └─► ctx.set_state("as3_app_marketing", {               │
│                "virtual_ip": "192.168.50.3"                     │
│             })                                                   │
│                                                                  │
│  ═══════════════════════════════════════════════════════════   │
│                                                                  │
│  Step 2: Select Pool Members (later in conversation)           │
│    User: "Use servers 1 and 2"                                  │
│    Claude → create_as3_app(pool_member_selection="1 and 2")   │
│         │                                                        │
│         ├─► ctx.get_state("as3_app_marketing")                 │
│         │   Result: { "virtual_ip": "192.168.50.3" }            │
│         │                                                        │
│         └─► Use cached VIP + selected pool members              │
│             Deploy AS3 app with both!                           │
│                                                                  │
│  ═══════════════════════════════════════════════════════════   │
│                                                                  │
│  Step 3: Clear State After Deployment                          │
│    ctx.set_state("as3_app_marketing", None)                    │
│    (Clean up for next app creation)                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Code Implementation

**Setting state:** `server.py:1490-1495` (would be set by phpIPAM interaction)
```python
state_key = f"as3_app_{section_name}"
app_state = ctx.get_state(state_key) if ctx else None

if app_state and app_state.get("virtual_ip"):
    virtual_ip = app_state["virtual_ip"]
    await ctx.info(f"Using cached VIP: {virtual_ip}")
```

**Clearing state after deployment:** `server.py:1659`
```python
# Clear cached state after successful deployment
if ctx:
    ctx.set_state(state_key, None)
```

**State key pattern:** `as3_app_{section_name}`
- `as3_app_marketing`
- `as3_app_engineering`
- `as3_app_finance`

### Context State Best Practices

1. **Use descriptive keys**: `bigip_token_{device_name}` not `token1`
2. **Include expiration**: Don't cache indefinitely
3. **Clear after use**: Clean up state when workflow completes
4. **Namespace by entity**: Device tokens, app state, user selections
5. **Handle missing state**: Always check if `get_state()` returns `None`

### State Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                   Context State Lifecycle                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Session Start                                              │
│       │                                                      │
│       ▼                                                      │
│  ┌────────────────┐                                         │
│  │  Empty Context │  ctx.get_state() → None                │
│  └────────────────┘                                         │
│       │                                                      │
│       │ First tool call                                     │
│       ▼                                                      │
│  ┌────────────────┐                                         │
│  │ Set State      │  ctx.set_state("key", data)            │
│  └────────────────┘                                         │
│       │                                                      │
│       │ Multiple subsequent calls                           │
│       ▼                                                      │
│  ┌────────────────┐                                         │
│  │ Get State      │  ctx.get_state("key") → data           │
│  │ (Reuse cached) │  (No re-computation!)                  │
│  └────────────────┘                                         │
│       │                                                      │
│       │ Workflow completes                                  │
│       ▼                                                      │
│  ┌────────────────┐                                         │
│  │ Clear State    │  ctx.set_state("key", None)            │
│  └────────────────┘                                         │
│       │                                                      │
│       │ Session ends                                        │
│       ▼                                                      │
│  ┌────────────────┐                                         │
│  │ State Destroyed│  All context cleared                   │
│  └────────────────┘                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Performance Impact

**Without Context State:**
```
Call 1: list_virtual_servers()  → Authenticate (2s) + Query (0.5s) = 2.5s
Call 2: manage_as3()            → Authenticate (2s) + Query (0.5s) = 2.5s
Call 3: create_as3_app()        → Authenticate (2s) + Deploy (3s) = 5s
Total: 10 seconds
```

**With Context State:**
```
Call 1: list_virtual_servers()  → Authenticate (2s) + Query (0.5s) = 2.5s [Cache token]
Call 2: manage_as3()            → Reuse token (0s) + Query (0.5s) = 0.5s
Call 3: create_as3_app()        → Reuse token (0s) + Deploy (3s) = 3s
Total: 6 seconds (40% faster!)
```

---

## Feature 5: Cross-Server Integration

**What:** Multiple MCP servers working together, coordinated by Claude.

**When to use:** Workflows that span multiple systems (e.g., phpIPAM + BIG-IP).

**Key insight:** Claude acts as the orchestrator between servers.

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Cross-Server Orchestration                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│                        ┌──────────────┐                              │
│                        │              │                              │
│                        │    Claude    │                              │
│                        │ (Orchestrator)│                             │
│                        │              │                              │
│                        └───────┬──────┘                              │
│                                │                                      │
│                  ┌─────────────┴─────────────┐                       │
│                  │                           │                       │
│                  ▼                           ▼                       │
│         ┌─────────────────┐         ┌─────────────────┐             │
│         │  phpIPAM Server │         │  BIG-IP Server  │             │
│         ├─────────────────┤         ├─────────────────┤             │
│         │ Tools:          │         │ Tools:          │             │
│         │ • list_sections │         │ • list_vs       │             │
│         │ • reserve_ip    │         │ • create_as3_app│             │
│         │ • get_subnets   │         │ • manage_as3    │             │
│         └────────┬────────┘         └────────┬────────┘             │
│                  │                           │                       │
│                  ▼                           ▼                       │
│         ┌─────────────────┐         ┌─────────────────┐             │
│         │   phpIPAM DB    │         │   BIG-IP Device │             │
│         └─────────────────┘         └─────────────────┘             │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Complete Workflow: Creating an AS3 Application

This demonstrates all 5 MCP features working together.

```
┌─────────────────────────────────────────────────────────────────────────┐
│         Complete AS3 Application Creation Workflow                       │
│            (All 5 MCP Features in Action)                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  USER: "Create a load balancer for the marketing department"           │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│  STEP 1: Claude loads guidance                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│    [Feature: PROMPTS]                                                   │
│    Claude loads: create_app_workflow prompt                             │
│    → Understands: Need to coordinate phpIPAM + BIG-IP                   │
│    → Knows: 5-step process to follow                                    │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│  STEP 2: List sections (phpIPAM Server)                                │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│    [Feature: CROSS-SERVER]                                              │
│    Claude → phpIPAM: list_sections()                                    │
│    Result: [                                                            │
│      {id: 1, name: "marketing"},                                        │
│      {id: 2, name: "engineering"}                                       │
│    ]                                                                     │
│                                                                          │
│    Claude: "Found sections: marketing, engineering. Which one?"         │
│    User: "Marketing"                                                    │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│  STEP 3: Reserve Virtual IP (phpIPAM Server)                           │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│    [Feature: CROSS-SERVER]                                              │
│    Claude → phpIPAM: reserve_ip_address(                               │
│      subnet_id="8",                                                     │
│      hostname="marketing-vip"                                           │
│    )                                                                     │
│    Result: "192.168.50.3"                                               │
│                                                                          │
│    [Feature: CONTEXT STATE]                                             │
│    BIG-IP ctx.set_state("as3_app_marketing", {                         │
│      "virtual_ip": "192.168.50.3"                                       │
│    })                                                                    │
│                                                                          │
│    Claude: "Reserved VIP: 192.168.50.3 ✓"                              │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│  STEP 4: Get pool member options (phpIPAM Server)                      │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│    [Feature: CROSS-SERVER]                                              │
│    Claude → phpIPAM: get_subnet_details(                               │
│      subnet_id="7",                                                     │
│      include_addresses=true                                             │
│    )                                                                     │
│    Result: [                                                            │
│      {ip: "172.16.100.3", hostname: "web-mkt-3"},                      │
│      {ip: "172.16.100.4", hostname: "web-mkt-4"},                      │
│      {ip: "172.16.100.5", hostname: "web-mkt-5"}                       │
│    ]                                                                     │
│                                                                          │
│    Claude: "Available servers:                                          │
│      1. 172.16.100.3 (web-mkt-3)                                       │
│      2. 172.16.100.4 (web-mkt-4)                                       │
│      3. 172.16.100.5 (web-mkt-5)                                       │
│      Which ones do you want?"                                           │
│                                                                          │
│    User: "Use 1 and 2"                                                  │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│  STEP 5: Check available templates (BIG-IP Server)                     │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│    [Feature: RESOURCES]                                                 │
│    Claude reads: templates://available                                  │
│    Result: Found "marketing" template                                   │
│                                                                          │
│    Claude reads: templates://marketing                                  │
│    Result: Template requires VIRTUAL_IP, POOL_MEMBER_1, POOL_MEMBER_2  │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│  STEP 6: Create AS3 application (BIG-IP Server)                        │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│    [Feature: CONTEXT STATE]                                             │
│    Retrieve cached VIP: ctx.get_state("as3_app_marketing")             │
│    → virtual_ip = "192.168.50.3"                                        │
│                                                                          │
│    [Feature: TOOLS]                                                     │
│    Claude → BIG-IP: create_as3_app(                                    │
│      device_name="lab-bigip",                                           │
│      section_name="marketing",                                          │
│      virtual_ip="192.168.50.3",        ← From cached state             │
│      pool_members=["172.16.100.3", "172.16.100.4"],                    │
│      auto_deploy=False                  ← Preview first                │
│    )                                                                     │
│                                                                          │
│    Tool internally:                                                     │
│      1. [CONTEXT STATE] Check for cached BIG-IP token                  │
│         ctx.get_state("bigip_token_lab-bigip")                         │
│                                                                          │
│      2. [RESOURCES] Load template: templates/marketing.json            │
│                                                                          │
│      3. Render template with variables:                                │
│         TENANT_NAME → "Marketing"                                       │
│         APP_NAME → "marketing_app"                                      │
│         VIRTUAL_IP → "192.168.50.3"                                     │
│         POOL_MEMBER_1 → "172.16.100.3"                                  │
│         POOL_MEMBER_2 → "172.16.100.4"                                  │
│                                                                          │
│      4. Return preview                                                  │
│                                                                          │
│    Claude: "Preview:                                                    │
│      Tenant: Marketing                                                  │
│      VIP: 192.168.50.3:80                                               │
│      Pool: 172.16.100.3:80, 172.16.100.4:80                            │
│      Ready to deploy?"                                                  │
│                                                                          │
│    User: "Yes, deploy it"                                               │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│  STEP 7: Deploy application (BIG-IP Server)                            │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│    [Feature: TOOLS]                                                     │
│    Claude → BIG-IP: create_as3_app(                                    │
│      ... same parameters ...                                            │
│      auto_deploy=True              ← Deploy now!                       │
│    )                                                                     │
│                                                                          │
│    Tool internally:                                                     │
│      1. [CONTEXT STATE] Reuse cached token (no re-auth!)               │
│      2. POST AS3 declaration to BIG-IP                                 │
│      3. Poll deployment status                                          │
│      4. [CONTEXT STATE] Clear cached VIP state                         │
│         ctx.set_state("as3_app_marketing", None)                       │
│                                                                          │
│    Result: "✅ Application deployed successfully!"                      │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                          │
│  FINAL RESULT:                                                          │
│    Marketing load balancer is live!                                    │
│    VIP: 192.168.50.3                                                    │
│    Pool: web-mkt-3, web-mkt-4                                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Feature Interactions Summary

| Step | Tools | Resources | Prompts | Context State | Cross-Server |
|------|-------|-----------|---------|---------------|--------------|
| 1. Load guidance | | | ✅ | | |
| 2. List sections | ✅ | | | | ✅ |
| 3. Reserve VIP | ✅ | | | ✅ Set | ✅ |
| 4. Get pool IPs | ✅ | | | | ✅ |
| 5. Check templates | | ✅ | | | |
| 6. Preview app | ✅ | ✅ | | ✅ Get | |
| 7. Deploy app | ✅ | | | ✅ Get/Clear | |

**Every feature is used at least once!**

### Cross-Server Communication Pattern

**Key concept:** MCP servers cannot directly call each other. Claude is the orchestrator.

#### Anti-Pattern (Won't Work)
```python
# In BIG-IP server.py - WRONG!
@mcp.tool
def create_as3_app(...):
    # Trying to call phpIPAM directly - NOT POSSIBLE
    vip = phpipam_server.reserve_ip(subnet_id)  # ❌ No direct access
```

#### Correct Pattern
```python
# In BIG-IP server.py - CORRECT
@mcp.tool
def create_as3_app(...):
    if not virtual_ip:
        # Return instructions for Claude
        return """
        To proceed, please use the phpIPAM MCP server to reserve a VIP:

        Call phpIPAM's reserve_ip_address tool with:
        - subnet_id: "8"
        - hostname: "marketing-vip"

        Then call this tool again with the reserved IP.
        """
```

**Claude sees this and:**
1. Calls phpIPAM server's `reserve_ip_address` tool
2. Gets result: "192.168.50.3"
3. Calls BIG-IP server's `create_as3_app` tool with `virtual_ip="192.168.50.3"`

### Direct Mode vs Guided Mode

This server supports **both** patterns:

**Guided Mode** (Claude orchestrates)
```python
# Step 1
create_as3_app(device="lab-bigip", section="marketing")
→ "Please reserve VIP from phpIPAM subnet 8"

# Claude calls phpIPAM, gets "192.168.50.3"

# Step 2
create_as3_app(device="lab-bigip", section="marketing",
               pool_member_selection="1 and 2")
→ "Preview: VIP 192.168.50.3, Pool: ..."
```

**Direct Mode** (User provides IPs)
```python
# Single call
create_as3_app(
    device="lab-bigip",
    section="marketing",
    virtual_ip="192.168.50.3",
    pool_members=["172.16.100.3", "172.16.100.4"],
    auto_deploy=True
)
→ "✅ Deployed!"
```

---

## Complete Workflow Diagram

This diagram shows how all 5 features work together in the AS3 application creation workflow.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                     Complete MCP Feature Workflow                                 │
│                  (Creating AS3 App with Cross-Server Integration)                 │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│                            USER starts conversation                               │
│                                     │                                             │
│                                     ▼                                             │
│                    ┌─────────────────────────────────┐                           │
│                    │   Feature 3: PROMPTS            │                           │
│                    │   Claude loads workflow guide   │                           │
│                    └────────────┬────────────────────┘                           │
│                                 │                                                 │
│                                 ▼                                                 │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 5: CROSS-SERVER (phpIPAM)                │                     │
│        │  Tool: list_sections() → ["marketing", ...]       │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         │ User selects: "marketing"                              │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 5: CROSS-SERVER (phpIPAM)                │                     │
│        │  Tool: reserve_ip_address(subnet=8)               │                     │
│        │  Result: "192.168.50.3"                           │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 4: CONTEXT STATE (BIG-IP)                │                     │
│        │  ctx.set_state("as3_app_marketing",               │                     │
│        │    {"virtual_ip": "192.168.50.3"})                │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 5: CROSS-SERVER (phpIPAM)                │                     │
│        │  Tool: get_subnet_details(subnet=7)               │                     │
│        │  Shows: Available web servers                     │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         │ User selects: "1 and 2"                                │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 2: RESOURCES (BIG-IP)                    │                     │
│        │  Read: templates://available                      │                     │
│        │  Read: templates://marketing                      │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 1: TOOLS (BIG-IP)                        │                     │
│        │  Call: create_as3_app(                            │                     │
│        │    device="lab-bigip",                            │                     │
│        │    section="marketing",                           │                     │
│        │    pool_member_selection="1 and 2"                │                     │
│        │  )                                                 │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         │ Tool internally does:                                  │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 4: CONTEXT STATE (BIG-IP)                │                     │
│        │  ctx.get_state("as3_app_marketing")               │                     │
│        │  → Retrieves VIP: "192.168.50.3"                  │                     │
│        │                                                    │                     │
│        │  ctx.get_state("bigip_token_lab-bigip")          │                     │
│        │  → Retrieves cached auth token                    │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Load template, render, generate preview          │                     │
│        │  Show preview to user                             │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         │ User: "Deploy it"                                      │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 1: TOOLS (BIG-IP)                        │                     │
│        │  Call: create_as3_app(..., auto_deploy=True)     │                     │
│        │  → POST AS3 declaration to BIG-IP                │                     │
│        │  → Poll deployment status                         │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         ▼                                                         │
│        ┌────────────────────────────────────────────────────┐                    │
│        │  Feature 4: CONTEXT STATE (BIG-IP)                │                     │
│        │  ctx.set_state("as3_app_marketing", None)        │                     │
│        │  → Clear cached VIP after deployment              │                     │
│        └────────────────┬───────────────────────────────────┘                    │
│                         │                                                         │
│                         ▼                                                         │
│                    ✅ SUCCESS!                                                    │
│            Application deployed to BIG-IP                                         │
│                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘

FEATURE USAGE COUNT:
┌──────────────────┬───────┐
│ Tools            │   3×  │
│ Resources        │   2×  │
│ Prompts          │   1×  │
│ Context State    │   4×  │
│ Cross-Server     │   3×  │
└──────────────────┴───────┘
```

---

## Code Location Reference

Quick reference for finding each MCP feature in the codebase.

### Tools (4 total)

| Tool Name | Line | Description |
|-----------|------|-------------|
| `list_virtual_servers` | 937-1067 | Query BIG-IP virtual servers |
| `list_bigip_devices` | 1069-1105 | List configured devices |
| `manage_as3` | 1107-1415 | Install/upgrade AS3 |
| `create_as3_app` | 1417-1682 | Create AS3 applications |

**Declaration pattern:**
```python
@mcp.tool
async def tool_name(param: type, ctx: Context = None) -> str:
    """Tool description"""
```

### Resources (3 total)

| Resource URI | Line | Description |
|--------------|------|-------------|
| `config://server` | 1684-1697 | Server metadata |
| `templates://available` | 1700-1743 | List all templates |
| `templates://{template_name}` | 1746-1768 | Specific template content |

**Declaration pattern:**
```python
@mcp.resource("resource://uri")
def resource_name() -> str:
    """Resource description"""
    return json.dumps(data, indent=2)
```

### Prompts (2 total)

| Prompt Name | Line | Description |
|-------------|------|-------------|
| `help_prompt` | 1775-1798 | General server help |
| `create_app_workflow` | 1801-1875 | AS3 workflow guide |

**Declaration pattern:**
```python
@mcp.prompt
def prompt_name() -> str:
    """Prompt description"""
    return """
    Multi-line prompt content...
    """
```

### Context State (Usage locations)

| Operation | Lines | Description |
|-----------|-------|-------------|
| Set token | 997, 1174, 1589 | Cache BIG-IP auth token |
| Get token | 974, 1151, 1577 | Retrieve cached token |
| Set VIP | 1490-1495 | Cache reserved VIP (intended) |
| Get VIP | 1490-1495 | Retrieve cached VIP |
| Clear state | 1659 | Clean up after deployment |

**Usage pattern:**
```python
# Set
ctx.set_state(key: str, value: dict)

# Get
data = ctx.get_state(key: str)  # Returns dict or None

# Clear
ctx.set_state(key: str, None)
```

### Helper Functions

| Function | Line | Purpose |
|----------|------|---------|
| `load_as3_template` | 697-716 | Load JSON template from file |
| `render_as3_template` | 719-740 | Replace {{VARIABLES}} in template |
| `validate_as3_declaration` | 743-760 | Validate AS3 JSON structure |
| `deploy_as3_declaration` | 800-851 | POST declaration to BIG-IP |
| `authenticate_bigip` | 177-215 | Get auth token from BIG-IP |

---

## Learning Path

Recommended order to study and understand MCP features:

### Level 1: Fundamentals
1. **Start with Tools** (You already know this!)
   - Read: `list_virtual_servers` (server.py:937-1067)
   - Understand: Tool declaration, parameters, return values
   - Practice: Call the tool via Claude

### Level 2: Data Access
2. **Study Resources**
   - Read: `list_available_templates` (server.py:1700-1743)
   - Read: `get_template_content` (server.py:1746-1768)
   - Understand: Read-only data access pattern
   - Practice: "Show me available templates"
   - Compare: When to use Resource vs Tool

### Level 3: User Guidance
3. **Explore Prompts**
   - Read: `create_app_workflow` (server.py:1801-1875)
   - Understand: How Claude uses prompts for guidance
   - Practice: Ask Claude "How do I create an AS3 app?"
   - Experiment: Try different phrasings to trigger the prompt

### Level 4: State Management
4. **Master Context State**
   - Read: Token caching logic (server.py:974-998)
   - Read: VIP caching logic (server.py:1490-1495)
   - Understand: State lifecycle (set → get → clear)
   - Practice: Make multiple tool calls, observe caching
   - Experiment: Time tool calls with/without caching

### Level 5: Advanced Integration
5. **Understand Cross-Server**
   - Read: `create_as3_app` tool (server.py:1417-1682)
   - Read: phpIPAM helper functions (server.py:763-930)
   - Understand: How Claude orchestrates between servers
   - Practice: Full workflow (guided mode)
   - Experiment: Try direct mode vs guided mode

### Level 6: Synthesis
6. **Complete Workflow**
   - Run the full AS3 application creation workflow
   - Observe all 5 features working together
   - Trace the execution through this guide
   - Identify each feature usage in the flow

---

## Additional Resources

### Official Documentation
- **MCP Specification**: https://modelcontextprotocol.io/docs/specification
- **FastMCP 2.0 Docs**: https://gofastmcp.com/

### This Codebase
- **README.md**: Project overview and setup
- **TEMPLATES.md**: Template system documentation
- **CONFIGURATION.md**: Device configuration guide
- **CLAUDE.md**: Usage examples

### Experimentation Tips

1. **Enable verbose logging**: See exactly what MCP calls Claude makes
2. **Use Claude Desktop devtools**: Monitor MCP communication
3. **Modify prompts**: See how it changes Claude's behavior
4. **Add new resources**: Practice exposing data
5. **Track state**: Add logging to see cache hits/misses

---

## Summary

This BIG-IP MCP server demonstrates **all major MCP features**:

| Feature | What It Does | Why It Matters |
|---------|--------------|----------------|
| **Tools** | Execute actions | Core functionality |
| **Resources** | Expose data catalogs | Efficient data access |
| **Prompts** | Guide Claude | Consistent UX |
| **Context State** | Cache session data | Performance + UX |
| **Cross-Server** | Coordinate systems | Complex workflows |

**Key Takeaway:** MCP is more than just tools. It's a complete protocol for building AI-powered integrations with performance, usability, and composability built in.

**Next Steps:**
1. Follow the [Learning Path](#learning-path) above
2. Experiment with each feature
3. Build your own MCP server using these patterns
4. Combine multiple MCP servers for complex workflows

Happy learning! 🚀
