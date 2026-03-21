# odoo-mcp

MCP server for Odoo Community ERP — AI Employee Gold Tier.

Exposes 5 tools to Claude Code for accounting integration:

| Tool | Description |
|------|-------------|
| `get_invoices` | List customer/vendor invoices with filters |
| `get_transactions` | List bank statement lines |
| `create_invoice_draft` | Create a draft invoice (does NOT post) |
| `get_monthly_summary` | Revenue + expense totals for a month |
| `get_partners` | List customers or vendors |

## Setup

### 1. Install Odoo Community

**Option A — Windows installer (easiest):**
- Download from https://www.odoo.com/page/download
- Select Odoo 17 Community → Windows
- Opens at http://localhost:8069

**Option B — Docker:**
```bash
docker run -d -p 8069:8069 \
  -e POSTGRES_USER=odoo \
  -e POSTGRES_PASSWORD=odoo \
  --name odoo odoo:17
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in:

```
ODOO_URL=http://localhost:8069
ODOO_DB=odoo
ODOO_USERNAME=admin
ODOO_PASSWORD=admin
```

### 3. Install dependencies

```bash
cd mcp-servers/odoo-mcp
npm install
```

### 4. Register in Claude Code settings

Add to `~/.claude/settings.json` (or `.claude/settings.json`):

```json
{
  "mcpServers": {
    "odoo": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-servers/odoo-mcp/index.js"],
      "env": {
        "ODOO_URL": "http://localhost:8069",
        "ODOO_DB": "odoo",
        "ODOO_USERNAME": "admin",
        "ODOO_PASSWORD": "admin"
      }
    }
  }
}
```

### 5. Test with DRY_RUN

```bash
DRY_RUN=true npm start
```

## Safety Rules

- `create_invoice_draft` only creates DRAFT invoices — it never posts them.
- Posting an invoice or recording a payment must go through `vault/Pending_Approval/`.
- Never store Odoo credentials in vault files.
