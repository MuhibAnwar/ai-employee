/**
 * email-mcp/index.js — Email MCP Server (Silver Tier)
 *
 * Exposes two MCP tools to Claude Code:
 *   • send_email  — send a message via Gmail API
 *   • draft_email — save a Gmail draft (returns draft ID)
 *
 * Authentication: OAuth2 via saved token file (same credentials as gmail_watcher.py).
 * Set DRY_RUN=true to log intent without actually calling Gmail.
 *
 * Register in Claude Code (~/.claude/settings.json):
 *   "mcpServers": {
 *     "email": {
 *       "command": "node",
 *       "args": ["./mcp-servers/email-mcp/index.js"],
 *       "env": { "GMAIL_TOKEN_PATH": "./secrets/gmail_token.json" }
 *     }
 *   }
 *
 * Usage:
 *   node mcp-servers/email-mcp/index.js
 *   DRY_RUN=true node mcp-servers/email-mcp/index.js
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { google } from "googleapis";
import fs from "fs";
import path from "path";

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

const DRY_RUN = process.env.DRY_RUN === "true";
const TOKEN_PATH = process.env.GMAIL_TOKEN_PATH || "./secrets/gmail_token.json";
const SCOPES = [
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/gmail.compose",
];

// ─────────────────────────────────────────────────────────────────────────────
// Gmail helpers
// ─────────────────────────────────────────────────────────────────────────────

function loadCredentials() {
  if (!fs.existsSync(TOKEN_PATH)) {
    throw new Error(
      `Gmail token not found at ${TOKEN_PATH}.\n` +
        "Run gmail_watcher.py once to complete OAuth flow and generate the token."
    );
  }
  const token = JSON.parse(fs.readFileSync(TOKEN_PATH, "utf-8"));
  const auth = new google.auth.OAuth2();
  auth.setCredentials(token);
  return auth;
}

function makeRawMessage({ to, subject, body, cc }) {
  const lines = [
    `To: ${to}`,
    cc ? `Cc: ${cc}` : null,
    `Subject: ${subject}`,
    "MIME-Version: 1.0",
    'Content-Type: text/plain; charset="UTF-8"',
    "",
    body,
  ]
    .filter((l) => l !== null)
    .join("\r\n");

  // Base64url encode
  return Buffer.from(lines)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

async function sendEmail({ to, subject, body, cc }) {
  if (DRY_RUN) {
    return {
      dry_run: true,
      message: `[DRY_RUN] Would send email to "${to}" | Subject: "${subject}"`,
    };
  }

  const auth = loadCredentials();
  const gmail = google.gmail({ version: "v1", auth });

  const raw = makeRawMessage({ to, subject, body, cc });
  const result = await gmail.users.messages.send({
    userId: "me",
    requestBody: { raw },
  });

  return {
    message_id: result.data.id,
    thread_id: result.data.threadId,
    status: "sent",
  };
}

async function draftEmail({ to, subject, body }) {
  if (DRY_RUN) {
    return {
      dry_run: true,
      message: `[DRY_RUN] Would create draft to "${to}" | Subject: "${subject}"`,
    };
  }

  const auth = loadCredentials();
  const gmail = google.gmail({ version: "v1", auth });

  const raw = makeRawMessage({ to, subject, body });
  const result = await gmail.users.drafts.create({
    userId: "me",
    requestBody: { message: { raw } },
  });

  return {
    draft_id: result.data.id,
    message_id: result.data.message?.id,
    status: "draft_created",
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP Server
// ─────────────────────────────────────────────────────────────────────────────

const server = new Server(
  { name: "email-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "send_email",
      description:
        "Send an email via Gmail. Always requires an approved action file in vault/Approved/ before calling. Set DRY_RUN=true during development.",
      inputSchema: {
        type: "object",
        properties: {
          to: {
            type: "string",
            description: "Recipient email address",
          },
          subject: {
            type: "string",
            description: "Email subject line",
          },
          body: {
            type: "string",
            description: "Plain-text email body",
          },
          cc: {
            type: "string",
            description: "Optional CC email address",
          },
        },
        required: ["to", "subject", "body"],
      },
    },
    {
      name: "draft_email",
      description:
        "Save an email as a Gmail draft without sending. Returns the draft ID. Useful for human review before sending.",
      inputSchema: {
        type: "object",
        properties: {
          to: {
            type: "string",
            description: "Recipient email address",
          },
          subject: {
            type: "string",
            description: "Email subject line",
          },
          body: {
            type: "string",
            description: "Plain-text email body",
          },
        },
        required: ["to", "subject", "body"],
      },
    },
  ],
}));

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    let result;

    if (name === "send_email") {
      const { to, subject, body, cc } = args;
      if (!to || !subject || !body) {
        throw new Error("send_email requires: to, subject, body");
      }
      result = await sendEmail({ to, subject, body, cc });
    } else if (name === "draft_email") {
      const { to, subject, body } = args;
      if (!to || !subject || !body) {
        throw new Error("draft_email requires: to, subject, body");
      }
      result = await draftEmail({ to, subject, body });
    } else {
      throw new Error(`Unknown tool: ${name}`);
    }

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (err) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${err.message}`,
        },
      ],
      isError: true,
    };
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Start
// ─────────────────────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(
    `Email MCP server started${DRY_RUN ? " [DRY_RUN mode]" : ""}`
  );
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
