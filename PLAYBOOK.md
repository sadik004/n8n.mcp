# n8n MCP Server: Operational Playbook & Recipes

This operational playbook provides step-by-step guidance, copy-paste prompts, and best practices for leveraging the **26 MCP tools** in `n8n-mcp`.

---

## 🎯 Table of Contents
1. [Recipe 1: Token-Optimized Diff-Patching](#recipe-1-token-optimized-diff-patching)
2. [Recipe 2: Safe Sandbox Testing with Pin-Data](#recipe-2-safe-sandbox-testing-with-pin-data)
3. [Recipe 3: Autonomous Self-Healing for Failed Executions](#recipe-3-autonomous-self-healing-for-failed-executions)
4. [Recipe 4: Anti-Bot Stealth Scraping via behavioral-playwright](#recipe-4-anti-bot-stealth-scraping-via-behavioral-playwright)
5. [Recipe 5: Multi-Port LangChain AI Agent Validation](#recipe-5-multi-port-langchain-ai-agent-validation)
6. [LLM Agent System Prompts](#llm-agent-system-prompts)

---

## 🛠️ Recipe 1: Token-Optimized Diff-Patching

### The Problem
Sending an entire workflow JSON back and forth to change an API endpoint or Slack channel burns 15,000–30,000 tokens per prompt, saturating LLM context windows in minutes.

### The Solution: `n8n_patch_node`
`n8n_patch_node` allows editing only the parameters you need. Sibling parameters and connections are untouched, and an automated pre-patch snapshot is saved locally.

### Example: Update Slack Notification Channel
```json
{
  "workflow_id": "WFlkj92841029",
  "node_name": "Slack Alert",
  "parameters": {
    "channel": "#incident-response",
    "text": ":rotating_light: Production error resolved: {{ $json.errorMessage }}"
  }
}
```

### Rollback on Mistake
If the updated parameters cause issues, restore the snapshot with 1 call:
```json
{
  "workflow_id": "WFlkj92841029"
}
```

---

## 🧪 Recipe 2: Safe Sandbox Testing with Pin-Data

### The Problem
Triggering live Stripe, Shopify, or Webhook nodes during development can fire unwanted downstream effects (emails, charges, database mutations).

### The Solution: `n8n_set_pinned_data`
Inject mock test payloads directly into the trigger node in n8n. The canvas can execute test runs using this pinned data without hitting external endpoints.

### Example: Injecting Mock Webhook Payload
```json
{
  "workflow_id": "WFlkj92841029",
  "node_name": "Webhook",
  "data": {
    "event": "customer.created",
    "customer": {
      "id": "cus_987654321",
      "email": "sarah.connor@example.com",
      "plan": "enterprise"
    }
  }
}
```

### Pre-Deployment Cleanup
Before pushing the workflow to production, clear the pinned data:
```json
{
  "workflow_id": "WFlkj92841029",
  "node_name": "Webhook"
}
```

---

## 🩺 Recipe 3: Autonomous Self-Healing for Failed Executions

### The Problem
When a cron or webhook triggers a workflow that crashes (e.g., HTTP 401 due to expired token, rate limits, or malformed JSON), manual triage takes hours.

### The Solution: `n8n_auto_heal_execution`
The autonomous self-healing loop:
1. Calls `n8n_audit_errors` to pinpoint the crashed node and parse the root cause (RCA).
2. Creates a pre-patch snapshot.
3. Patches the crashed node with corrected parameters or credentials.
4. Triggers `n8n_retry_execution(load_workflow=True)`.
5. Verifies if the retry succeeds. If not, it attempts a second repair (strictly bounded to 2 attempts to prevent infinite loops).

### Example: Repairing a Crashed HTTP Request Node
```json
{
  "execution_id": "782910",
  "repair_parameters": {
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth"
  }
}
```

---

## 🕷️ Recipe 4: Anti-Bot Stealth Scraping via behavioral-playwright

### The Problem
Scraping Reddit, LinkedIn, Twitter, or Cloudflare-protected sites from standard n8n HTTP Request nodes triggers instant 403 Forbidden or Turnstile CAPTCHAs.

### The Solution: `n8n_create_stealth_scraper_node`
Generates a pre-configured `httpRequest` node communicating with the local `behavioral-playwright` evasion bridge (running on `http://host.docker.internal:8000`).

### Generated Node Specifications:
- **Biomechanical Mouse Tremor**: Simulates human curve movements and micro-hesitations.
- **Route-Level Asset Abortion**: Discards stylesheets, fonts, and tracking images for 70% lower bandwidth.
- **Residential Header Spoofing**: Perfectly aligned Client Hints, WebGL fingerprints, and cipher suites.

### Example: Adding a Stealth Scraper Node
```json
{
  "node_name": "Reddit Lead Scraper",
  "target_url": "https://reddit.com/r/freelance/new",
  "selector": "shreddit-post",
  "position": [450, 200]
}
```

---

## 🤖 Recipe 5: Multi-Port LangChain AI Agent Validation

### The Problem
In n8n, LangChain nodes do NOT use standard `main` connections. Connecting an OpenAI Chat Model to the `main` input of an AI Agent silently fails.

### The Solution: `n8n_validate_ai_agent_graph`
Validates that:
1. Every `agent` or `chainLlm` node has an incoming connection on `ai_languageModel`.
2. Attached Tools are connected on the `ai_tool` port.
3. Attached Memory buffers are connected on the `ai_memory` port.

### Example Validation Call
```json
{
  "workflow": {
    "name": "Customer Support Agent",
    "nodes": [ ... ],
    "connections": { ... }
  }
}
```

Returns actionable error diagnostics if the language model sub-node is missing or incorrectly routed.

---

## 💡 LLM Agent System Prompts

Add this prompt block to your Claude Desktop or Cursor Custom Instructions to enforce optimal tool usage:

```text
You are an expert n8n Automation Architect connected to n8n MCP Server.
Always follow these engineering principles:
1. NEVER overwrite an entire workflow just to edit a single node. Always use 'n8n_patch_node' for token efficiency (85-90% savings).
2. When creating new nodes, use 'n8n_get_node_schema' first to verify exact property names, enums, and required parameters to prevent hallucination.
3. Before deploying any workflow, validate it with 'n8n_validate_workflow' to catch DAG cycles, unclosed {{ }} expressions, and invalid Python ASTs.
4. When testing workflows, inject mock inputs using 'n8n_set_pinned_data' rather than running live triggers.
5. If an execution fails, use 'n8n_audit_errors' for root cause analysis, or 'n8n_auto_heal_execution' to patch and retry automatically.
```
