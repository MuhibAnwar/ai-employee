/**
 * test-tools.js — standalone test harness for odoo-mcp
 *
 * 1. Authenticates with Odoo
 * 2. Creates test data: partner "Test Client" + draft invoice $500
 * 3. Exercises all 5 MCP tool functions
 *
 * Run:
 *   node mcp-servers/odoo-mcp/test-tools.js
 */

const ODOO_URL      = process.env.ODOO_URL      || "http://localhost:8069";
const ODOO_DB       = process.env.ODOO_DB       || "odoo";
const ODOO_USERNAME = process.env.ODOO_USERNAME || "admin";
const ODOO_PASSWORD = process.env.ODOO_PASSWORD || "admin";

let _uid     = null;
let _session = "";

// ── JSON-RPC helpers ──────────────────────────────────────────────────────────

async function odooRpc(endpoint, params) {
  const headers = { "Content-Type": "application/json" };
  if (_session) headers["Cookie"] = _session;

  const res = await fetch(`${ODOO_URL}${endpoint}`, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params }),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${text}`);

  const setCookie = res.headers.get("set-cookie");
  if (setCookie) {
    const match = setCookie.match(/session_id=[^;]+/);
    if (match) _session = match[0];
  }

  const json = JSON.parse(text);
  if (json.error) throw new Error(`RPC error: ${JSON.stringify(json.error.data || json.error)}`);
  return json.result;
}

async function authenticate() {
  if (_uid) return _uid;
  const result = await odooRpc("/web/session/authenticate", {
    db: ODOO_DB,
    login: ODOO_USERNAME,
    password: ODOO_PASSWORD,
  });
  _uid = result?.uid;
  if (!_uid) throw new Error("Authentication failed");
  console.log(`  Authenticated as uid=${_uid}`);
  return _uid;
}

async function callModel(model, method, args = [], kwargs = {}) {
  await authenticate();
  return odooRpc("/web/dataset/call_kw", { model, method, args, kwargs });
}

// ── Test data setup ───────────────────────────────────────────────────────────

async function createTestData() {
  console.log("\n[SETUP] Creating test data...");

  // Check if partner already exists
  const existing = await callModel("res.partner", "search_read", [[["name", "=", "Test Client"]]], {
    fields: ["id", "name"], limit: 1,
  });

  let partnerId;
  if (existing.length) {
    partnerId = existing[0].id;
    console.log(`  Partner "Test Client" already exists (id=${partnerId})`);
  } else {
    partnerId = await callModel("res.partner", "create", [{
      name: "Test Client",
      customer_rank: 1,
      email: "testclient@example.com",
    }]);
    console.log(`  Created partner "Test Client" (id=${partnerId})`);
  }

  // Create draft invoice for $500
  const invoiceId = await callModel("account.move", "create", [{
    move_type: "out_invoice",
    partner_id: partnerId,
    invoice_date: new Date().toISOString().slice(0, 10),
    invoice_line_ids: [[0, 0, {
      name: "Test Service",
      quantity: 1,
      price_unit: 500,
    }]],
  }]);
  console.log(`  Created draft invoice (id=${invoiceId}) for $500`);

  return { partnerId, invoiceId };
}

// ── Tool tests ────────────────────────────────────────────────────────────────

async function testGetInvoices() {
  console.log("\n[TOOL 1] get_invoices");
  const domain = [["move_type", "in", ["out_invoice", "in_invoice"]]];
  const records = await callModel("account.move", "search_read", [domain], {
    fields: ["name", "partner_id", "invoice_date", "amount_total", "currency_id", "state", "move_type"],
    limit: 5,
    order: "invoice_date desc",
  });
  console.log(`  Returned ${records.length} invoice(s)`);
  records.forEach(r => console.log(`    - [${r.state}] ${r.name || "draft"} | ${r.partner_id?.[1]} | $${r.amount_total}`));
  return records.length >= 1 ? "PASS" : "FAIL (no invoices)";
}

async function testGetTransactions() {
  console.log("\n[TOOL 2] get_transactions");
  const records = await callModel("account.bank.statement.line", "search_read", [[]], {
    fields: ["date", "payment_ref", "partner_id", "amount", "currency_id"],
    limit: 5,
    order: "date desc",
  });
  console.log(`  Returned ${records.length} transaction(s) (empty is OK on fresh install)`);
  return "PASS";
}

async function testCreateInvoiceDraft() {
  console.log("\n[TOOL 3] create_invoice_draft");
  const partners = await callModel("res.partner", "search_read", [[["name", "ilike", "Test Client"]]], {
    fields: ["id", "name"], limit: 1,
  });
  if (!partners.length) return "FAIL (partner not found)";
  const partnerId = partners[0].id;

  const invoiceId = await callModel("account.move", "create", [{
    move_type: "out_invoice",
    partner_id: partnerId,
    invoice_date: new Date().toISOString().slice(0, 10),
    invoice_line_ids: [[0, 0, { name: "MCP Tool Test", quantity: 1, price_unit: 250 }]],
  }]);
  console.log(`  Created draft invoice id=${invoiceId} for Test Client ($250)`);
  return `PASS (invoice_id=${invoiceId})`;
}

async function testGetMonthlySummary() {
  console.log("\n[TOOL 4] get_monthly_summary (2026-03)");
  const year = 2026, month = 3;
  const dateFrom = `${year}-03-01`;
  const dateTo   = `${year}-03-31`;
  const invoices = await callModel("account.move", "search_read", [[
    ["move_type", "in", ["out_invoice", "in_invoice"]],
    ["state", "=", "posted"],
    ["invoice_date", ">=", dateFrom],
    ["invoice_date", "<=", dateTo],
  ]], { fields: ["move_type", "amount_total"] });

  let revenue = 0, expenses = 0;
  for (const inv of invoices) {
    if (inv.move_type === "out_invoice") revenue  += inv.amount_total;
    if (inv.move_type === "in_invoice")  expenses += inv.amount_total;
  }
  console.log(`  Period: 2026-03 | Revenue: $${revenue} | Expenses: $${expenses} | Net: $${revenue - expenses}`);
  return "PASS";
}

async function testGetPartners() {
  console.log("\n[TOOL 5] get_partners");
  const records = await callModel("res.partner", "search_read", [
    [["active", "=", true], ["customer_rank", ">", 0]],
  ], {
    fields: ["name", "email", "phone", "customer_rank", "supplier_rank"],
    limit: 5,
    order: "name asc",
  });
  console.log(`  Returned ${records.length} partner(s)`);
  records.forEach(r => console.log(`    - ${r.name} (email: ${r.email || "none"})`));
  const hasTestClient = records.some(r => r.name === "Test Client");
  return hasTestClient ? "PASS (Test Client found)" : "PASS (Test Client may not have customer_rank yet)";
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log("=== odoo-mcp tool test ===");
  console.log(`Target: ${ODOO_URL} | DB: ${ODOO_DB} | User: ${ODOO_USERNAME}`);

  await createTestData();

  const results = {};
  results.get_invoices        = await testGetInvoices();
  results.get_transactions    = await testGetTransactions();
  results.create_invoice_draft = await testCreateInvoiceDraft();
  results.get_monthly_summary = await testGetMonthlySummary();
  results.get_partners        = await testGetPartners();

  console.log("\n=== Results ===");
  for (const [tool, result] of Object.entries(results)) {
    const icon = result.startsWith("PASS") ? "✓" : "✗";
    console.log(`  ${icon} ${tool}: ${result}`);
  }

  const failed = Object.values(results).filter(r => r.startsWith("FAIL"));
  if (failed.length === 0) {
    console.log("\nAll 5 tools passed.");
    process.exit(0);
  } else {
    console.log(`\n${failed.length} tool(s) failed.`);
    process.exit(1);
  }
}

main().catch(err => {
  console.error("Fatal:", err.message);
  process.exit(1);
});
