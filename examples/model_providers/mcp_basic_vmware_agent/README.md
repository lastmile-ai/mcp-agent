# MCP VMware AIops Agent example

This example shows a VMware infrastructure management agent using [vmware-aiops](https://github.com/zw008/VMware-AIops) — an MCP server for VMware vCenter/ESXi operations.

The agent can query VM inventory, check active alarms, inspect datastores, manage VM lifecycle, and run guest commands — all through natural language.

## `1` Prerequisites

### Install vmware-aiops

```bash
uv tool install vmware-aiops
```

### Configure vCenter/ESXi credentials

```bash
mkdir -p ~/.vmware-aiops
cat > ~/.vmware-aiops/config.yaml << 'EOF'
targets:
  my-vcenter:
    host: vcenter.example.com
    username: administrator@vsphere.local
    password_env: VMWARE_PASSWORD
    verify_ssl: false
EOF

echo "VMWARE_PASSWORD=your_password" > ~/.vmware-aiops/.env
chmod 600 ~/.vmware-aiops/.env
```

Verify connectivity:

```bash
vmware-aiops doctor
```

## `2` App set up

Clone the repo and navigate to this example:

```bash
git clone https://github.com/lastmile-ai/mcp-agent.git
cd mcp-agent/examples/model_providers/mcp_basic_vmware_agent
```

Install `uv` (if you don't have it):

```bash
pip install uv
```

Sync `mcp-agent` project dependencies:

```bash
uv sync
```

Install requirements specific to this example:

```bash
uv pip install -r requirements.txt
```

Update `mcp_agent.config.yaml` — set `cwd` to your VMware-AIops installation path:

```yaml
mcp:
  servers:
    vmware-aiops:
      command: python
      args: [-m, mcp_server]
      cwd: /path/to/VMware-AIops   # ← update this
```

Set your Anthropic API key:

```bash
cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml
# Edit mcp_agent.secrets.yaml and add your ANTHROPIC_API_KEY
```

## `3` Run locally

```bash
uv run main.py
```

The agent will:
1. Connect to your vCenter/ESXi via the vmware-aiops MCP server
2. Run a health overview (active alarms by severity)
3. List top 5 VMs by memory usage
4. Check datastores above 80% capacity and investigate the most critical one

## Available MCP tools

vmware-aiops exposes 31 tools across 7 categories:

| Category | Tools |
|----------|-------|
| Inventory | `list_virtual_machines`, `list_esxi_hosts`, `list_all_datastores`, `list_all_clusters` |
| Health | `get_alarms`, `get_events`, `vm_info` |
| VM Lifecycle | `vm_power_on`, `vm_power_off`, `vm_set_ttl`, `vm_cancel_ttl`, `vm_list_ttl`, `vm_clean_slate` |
| Deployment | `deploy_vm_from_ova`, `deploy_vm_from_template`, `deploy_linked_clone`, and more |
| Guest Operations | `vm_guest_exec`, `vm_guest_upload`, `vm_guest_download` |
| Plan → Apply | `vm_create_plan`, `vm_apply_plan`, `vm_rollback_plan`, `vm_list_plans` |
| Datastore | `browse_datastore`, `scan_datastore_images`, `list_cached_images` |

For read-only monitoring (zero destructive operations), use [vmware-monitor](https://github.com/zw008/VMware-Monitor) instead.
