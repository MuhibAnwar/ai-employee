/**
 * odoo-mcp/index.js
 * MCP server for Odoo Community ERP — AI Employee Gold Tier
 *
 * Exposes read-only and draft-only accounting tools to Claude Code.
 * All write operations (post invoice, record payment) require human
 * approval via the vault/Pending_Approval/ workflow before execution.
 *
 * Odoo JSON-RPC 2.0 API docs:
 *   https://www.odoo.com/documentation/19.0/developer/reference/external_api.html
 *
 * Setup:
 *   1. Install Odoo Community (local or cloud)
 *   2. Set ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in .env
 *   3. npm install && npm start
 *   4. Register in Claude Code settings (see README.md)
 *
 * Tools provided:
 *   - get_invoices          List invoices with optional filters
 *   - get_transactions      List journal entries / bank transactions
 *   - create_invoice_draft  Create a draft invoice (does NOT post it)
 *   - get_monthly_summary   Revenue + expense totals for a given month
 *   - get_partners          List customers / vendors
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// ── Config ────────────────────────────────────────────────────────────────────

const ODOO_URL      = process.env.ODOO_URL      || "http://localhost:8069";
const ODOO_DB       = process.env.ODOO_DB       || "odoo";
const ODOO_USERNAME = process.env.ODOO_USERNAME || "admin";
const ODOO_PASSWORD = process.env.ODOO_PASSWORD || "admin";
const DRY_RUN       = process.env.DRY_RUN === "true";

// ── Odoo JSON-RPC helpers ──────────────────────────────────────────────────────

let _uid     = null; // cached user ID after authentication
let _session = "";   // session_id cookie carried across requests

/**
 * Make a raw JSON-RPC 2.0 call to Odoo.
 * Automatically carries the session cookie once authenticated.
 */
async function odooRpc(endpoint, params) {
  const headers = { "Content-Type": "application/json" };
  if (_session) headers["Cookie"] = _session;

  const res = await fetch(`${ODOO_URL}${endpoint}`, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params }),
  });

  if (!res.ok) {
    throw new Error(`Odoo HTTP error ${res.status}: ${await res.text()}`);
  }

  // Capture session cookie on first auth response
  const setCookie = res.headers.get("set-cookie");
  if (setCookie) {
    const match = setCookie.match(/session_id=[^;]+/);
    if (match) _session = match[0];
  }

  const json = await res.json();
  if (json.error) {
    throw new Error(`Odoo RPC error: ${JSON.stringify(json.error)}`);
  }
  return json.result;
}

/**
 * Authenticate and return the user ID (cached after first call).
 */
async function authenticate() {
  if (_uid !== null) return _uid;
  const result = await odooRpc("/web/session/authenticate", {
    db: ODOO_DB,
    login: ODOO_USERNAME,
    password: ODOO_PASSWORD,
  });
  _uid = result?.uid;
  if (!_uid) throw new Error("Odoo authentication failed — check credentials in .env");
  return _uid;
}

/**
 * Call an Odoo model method (search_read, create, etc.).
 */
async function callModel(model, method, args = [], kwargs = {}) {
  await authenticate();
  return odooRpc("/web/dataset/call_kw", {
    model,
    method,
    args,
    kwargs,
  });
}

// ── Tool implementations ───────────────────────────────────────────────────────

/**
 * get_invoices — list customer/vendor invoices with optional filters.
 *
 * @param {object} args
 * @param {string} [args.state]        - "draft" | "posted" | "cancel"
 * @param {string} [args.move_type]    - "out_invoice" (customer) | "in_invoice" (vendor)
 * @param {number} [args.limit]        - max records (default 20)
 * @param {string} [args.date_from]    - YYYY-MM-DD
 * @param {string} [args.date_to]      - YYYY-MM-DD
 */
async function getInvoices({ state, move_type, limit = 20, date_from, date_to } = {}) {
  if (DRY_RUN) {
    return "[DRY RUN] get_invoices called — would query Odoo account.move";
  }

  const domain = [["move_type", "in", ["out_invoice", "in_invoice"]]];
  if (state)     domain.push(["state", "=", state]);
  if (move_type) domain.push(["move_type", "=", move_type]);
  if (date_from) domain.push(["invoice_date", ">=", date_from]);
  if (date_to)   domain.push(["invoice_date", "<=", date_to]);

  const records = await callModel("account.move", "search_read", [domain], {
    fields: ["name", "partner_id", "invoice_date", "amount_total", "currency_id", "state", "move_type"],
    limit,
    order: "invoice_date desc",
  });

  return JSON.stringify(records, null, 2);
}

/**
 * get_transactions — list bank / journal transactions.
 *
 * @param {object} args
 * @param {number} [args.limit]     - max records (default 20)
 * @param {string} [args.date_from] - YYYY-MM-DD
 * @param {string} [args.date_to]   - YYYY-MM-DD
 */
async function getTransactions({ limit = 20, date_from, date_to } = {}) {
  if (DRY_RUN) {
    return "[DRY RUN] get_transactions called — would query Odoo account.bank.statement.line";
  }

  const domain = [];
  if (date_from) domain.push(["date", ">=", date_from]);
  if (date_to)   domain.push(["date", "<=", date_to]);

  const records = await callModel("account.bank.statement.line", "search_read", [domain], {
    fields: ["date", "payment_ref", "partner_id", "amount", "currency_id", "state"],
    limit,
    order: "date desc",
  });

  return JSON.stringify(records, null, 2);
}

/**
 * create_invoice_draft — create a DRAFT invoice in Odoo (does NOT post it).
 * Posting requires human approval via vault/Pending_Approval/.
 *
 * @param {object} args
 * @param {string} args.partner_name   - Customer name (must exist in Odoo)
 * @param {string} args.description    - Invoice line description
 * @param {number} args.amount         - Unit price (tax-exclusive)
 * @param {string} [args.currency]     - ISO currency code, default "USD"
 * @param {string} [args.date]         - Invoice date YYYY-MM-DD (default today)
 */
async function createInvoiceDraft({ partner_name, description, amount, currency = "USD", date } = {}) {
  if (!partner_name || !description || amount === undefined) {
    throw new Error("partner_name, description, and amount are required");
  }

  if (DRY_RUN) {
    return `[DRY RUN] create_invoice_draft — would create draft invoice for "${partner_name}" (${currency} ${amount}) in Odoo`;
  }

  // Resolve partner ID
  const partners = await callModel("res.partner", "search_read", [[["name", "ilike", partner_name]]], {
    fields: ["id", "name"],
    limit: 1,
  });
  if (!partners.length) throw new Error(`Partner not found in Odoo: "${partner_name}"`);
  const partnerId = partners[0].id;

  // Resolve currency ID
  const currencies = await callModel("res.currency", "search_read", [[["name", "=", currency.toUpperCase()]]], {
    fields: ["id"],
    limit: 1,
  });
  const currencyId = currencies[0]?.id;

  const invoiceVals = {
    move_type: "out_invoice",
    partner_id: partnerId,
    invoice_date: date || new Date().toISOString().slice(0, 10),
    currency_id: currencyId,
    invoice_line_ids: [[0, 0, {
      name: description,
      quantity: 1,
      price_unit: amount,
    }]],
  };

  const invoiceId = await callModel("account.move", "create", [invoiceVals]);
  return JSON.stringify({ status: "draft_created", invoice_id: invoiceId, partner: partners[0].name, amount, currency });
}

/**
 * get_monthly_summary — revenue and expense totals for a given month.
 *
 * @param {object} args
 * @param {number} args.year   - e.g. 2026
 * @param {number} args.month  - 1-12
 */
async function getMonthlySummary({ year, month } = {}) {
  if (!year || !month) throw new Error("year and month are required");

  if (DRY_RUN) {
    return `[DRY RUN] get_monthly_summary — would query Odoo account.move for ${year}-${String(month).padStart(2, "0")}`;
  }

  const dateFrom = `${year}-${String(month).padStart(2, "0")}-01`;
  const lastDay  = new Date(year, month, 0).getDate();
  const dateTo   = `${year}-${String(month).padStart(2, "0")}-${lastDay}`;

  const invoices = await callModel("account.move", "search_read", [[
    ["move_type", "in", ["out_invoice", "in_invoice"]],
    ["state", "=", "posted"],
    ["invoice_date", ">=", dateFrom],
    ["invoice_date", "<=", dateTo],
  ]], {
    fields: ["move_type", "amount_total", "currency_id"],
  });

  let revenue = 0, expenses = 0;
  for (const inv of invoices) {
    if (inv.move_type === "out_invoice") revenue  += inv.amount_total;
    if (inv.move_type === "in_invoice")  expenses += inv.amount_total;
  }

  return JSON.stringify({
    period: `${year}-${String(month).padStart(2, "0")}`,
    revenue,
    expenses,
    net: revenue - expenses,
    invoice_count: invoices.length,
  }, null, 2);
}

/**
 * get_partners — list customers or vendors.
 *
 * @param {object} args
 * @param {string} [args.type]    - "customer" | "vendor" | "all" (default "all")
 * @param {string} [args.search]  - name fragment to filter
 * @param {number} [args.limit]   - max records (default 20)
 */
async function getPartners({ type = "all", search, limit = 20 } = {}) {
  if (DRY_RUN) {
    return "[DRY RUN] get_partners called — would query Odoo res.partner";
  }

  const domain = [["active", "=", true]];
  if (type === "customer") domain.push(["customer_rank", ">", 0]);
  if (type === "vendor")   domain.push(["supplier_rank", ">", 0]);
  if (search)              domain.push(["name", "ilike", search]);

  const records = await callModel("res.partner", "search_read", [domain], {
    fields: ["name", "email", "phone", "customer_rank", "supplier_rank"],
    limit,
    order: "name asc",
  });

  return JSON.stringify(records, null, 2);
}

// ── MCP Server setup ───────────────────────────────────────────────────────────

const server = new Server(
  { name: "odoo-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "get_invoices",
      description: "List invoices from Odoo. Filter by state (draft/posted/cancel), type (customer/vendor), and date range.",
      inputSchema: {
        type: "object",
        properties: {
          state:     { type: "string", enum: ["draft", "posted", "cancel"], description: "Invoice state" },
          move_type: { type: "string", enum: ["out_invoice", "in_invoice"], description: "out_invoice=customer, in_invoice=vendor" },
          limit:     { type: "number", description: "Max records to return (default 20)" },
          date_from: { type: "string", description: "Start date YYYY-MM-DD" },
          date_to:   { type: "string", description: "End date YYYY-MM-DD" },
        },
      },
    },
    {
      name: "get_transactions",
      description: "List bank statement lines / transactions from Odoo.",
      inputSchema: {
        type: "object",
        properties: {
          limit:     { type: "number", description: "Max records (default 20)" },
          date_from: { type: "string", description: "Start date YYYY-MM-DD" },
          date_to:   { type: "string", description: "End date YYYY-MM-DD" },
        },
      },
    },
    {
      name: "create_invoice_draft",
      description: "Create a DRAFT invoice in Odoo. Does NOT post it — posting requires human approval.",
      inputSchema: {
        type: "object",
        required: ["partner_name", "description", "amount"],
        properties: {
          partner_name: { type: "string", description: "Customer name (must exist in Odoo)" },
          description:  { type: "string", description: "Invoice line description" },
          amount:       { type: "number", description: "Unit price (tax-exclusive)" },
          currency:     { type: "string", description: "ISO currency code (default USD)" },
          date:         { type: "string", description: "Invoice date YYYY-MM-DD (default today)" },
        },
      },
    },
    {
      name: "get_monthly_summary",
      description: "Get revenue and expense totals for a specific month from Odoo.",
      inputSchema: {
        type: "object",
        required: ["year", "month"],
        properties: {
          year:  { type: "number", description: "e.g. 2026" },
          month: { type: "number", description: "1-12" },
        },
      },
    },
    {
      name: "get_partners",
      description: "List customers or vendors from Odoo.",
      inputSchema: {
        type: "object",
        properties: {
          type:   { type: "string", enum: ["customer", "vendor", "all"], description: "Filter by role (default all)" },
          search: { type: "string", description: "Name fragment to filter" },
          limit:  { type: "number", description: "Max records (default 20)" },
        },
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    let result;
    switch (name) {
      case "get_invoices":        result = await getInvoices(args);        break;
      case "get_transactions":    result = await getTransactions(args);    break;
      case "create_invoice_draft": result = await createInvoiceDraft(args); break;
      case "get_monthly_summary": result = await getMonthlySummary(args);  break;
      case "get_partners":        result = await getPartners(args);        break;
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
    return { content: [{ type: "text", text: result }] };
  } catch (err) {
    return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
  }
});

// ── Start ──────────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
console.error(`odoo-mcp started — URL: ${ODOO_URL} | DB: ${ODOO_DB} | DRY_RUN: ${DRY_RUN}`);
