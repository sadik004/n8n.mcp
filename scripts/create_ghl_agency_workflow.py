#!/usr/bin/env python3
"""
Create and deploy GoHighLevel Agency Lead Qualifier & VIP Responder workflow in local n8n.
"""

import asyncio
import json
import httpx
import uuid

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from n8n_mcp.config import N8nConfig
from n8n_mcp.engine.client import N8nClient


async def main():
    config = N8nConfig()
    client = N8nClient(config=config)

    webhook_id = str(uuid.uuid4())
    normalize_id = str(uuid.uuid4())
    score_id = str(uuid.uuid4())
    if_id = str(uuid.uuid4())
    vip_alert_id = str(uuid.uuid4())
    vip_resp_id = str(uuid.uuid4())
    nurture_id = str(uuid.uuid4())
    nurture_resp_id = str(uuid.uuid4())

    workflow_payload = {
        "name": "[GHL Agency] AI Lead Qualifier & Instant VIP Responder",
        "nodes": [
            {
                "id": webhook_id,
                "name": "GHL Webhook Ingest",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [240, 300],
                "parameters": {
                    "httpMethod": "POST",
                    "path": "ghl-inbound-lead",
                    "responseMode": "responseNode",
                    "options": {}
                }
            },
            {
                "id": normalize_id,
                "name": "Normalize Lead Payload",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [480, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": """const raw = $json.body || $json;

let rawPhone = String(raw.phone || '');
let cleanPhone = rawPhone.replace(/[^\\d+]/g, '');
if (cleanPhone.length === 10 && !cleanPhone.startsWith('+')) {
  cleanPhone = '+1' + cleanPhone;
}

const firstName = (raw.first_name || raw.firstName || (raw.name ? raw.name.split(' ')[0] : 'Valued')).trim();
const lastName = (raw.last_name || raw.lastName || (raw.name ? raw.name.split(' ').slice(1).join(' ') : 'Client')).trim();
const email = (raw.email || '').toLowerCase().trim();
const company = (raw.company_name || raw.company || raw.business || 'Independent').trim();
const monthlyRevenue = Number(raw.monthly_revenue || raw.budget || 0);
const serviceNeeded = raw.service_needed || raw.service || 'AI Automation & CRM Integration';

return {
  json: {
    lead_id: 'GHL-' + Date.now().toString(36).toUpperCase(),
    first_name: firstName,
    last_name: lastName,
    full_name: `${firstName} ${lastName}`.trim(),
    email: email,
    phone: cleanPhone,
    company: company,
    monthly_revenue: monthlyRevenue,
    service_needed: serviceNeeded,
    source: raw.source || 'GoHighLevel Funnel',
    received_at: new Date().toISOString()
  }
};"""
                }
            },
            {
                "id": score_id,
                "name": "AI Lead Qualification & Scoring",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [720, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": """const lead = $json;
let score = 50;
let priority = "STANDARD";
let rationale = [];

if (lead.monthly_revenue >= 10000) {
  score += 35;
  rationale.push("High revenue potential (>$10k/mo)");
} else if (lead.monthly_revenue >= 3000) {
  score += 20;
  rationale.push("Mid-tier budget ($3k-$10k)");
} else if (lead.monthly_revenue > 0) {
  score += 10;
}

if (lead.phone && lead.phone.length >= 10) {
  score += 10;
  rationale.push("Verified phone number provided");
}

if (lead.email && !lead.email.endsWith('@gmail.com') && !lead.email.endsWith('@yahoo.com') && !lead.email.endsWith('@hotmail.com')) {
  score += 15;
  rationale.push("Business domain email address");
}

if (score >= 80) {
  priority = "VIP_HOT";
} else if (score >= 60) {
  priority = "WARM";
} else {
  priority = "NURTURE";
}

const personalizedPitch = `Hi ${lead.first_name}, noticed your inquiry on ${lead.service_needed} for ${lead.company}. We engineered a custom GoHighLevel AI pipeline that cuts manual follow-up time by 80%. When is best for a quick 10-min demo?`;

return {
  json: {
    ...lead,
    qualification: {
      lead_score: score,
      priority: priority,
      is_vip: score >= 80,
      scoring_factors: rationale,
      suggested_pitch: personalizedPitch,
      sla_followup_minutes: priority === "VIP_HOT" ? 5 : 60
    }
  }
};"""
                }
            },
            {
                "id": if_id,
                "name": "Check Priority (Is VIP?)",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [960, 300],
                "parameters": {
                    "conditions": {
                        "options": {
                            "caseSensitive": True,
                            "leftValue": "",
                            "typeValidation": "strict"
                        },
                        "conditions": [
                            {
                                "id": "cond-vip",
                                "leftValue": "={{ $json.qualification.is_vip }}",
                                "rightValue": True,
                                "operator": {
                                    "type": "boolean",
                                    "operation": "equals"
                                }
                            }
                        ],
                        "combinator": "and"
                    }
                }
            },
            {
                "id": vip_alert_id,
                "name": "Dispatch Instant VIP Alert",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1220, 180],
                "parameters": {
                    "method": "POST",
                    "url": "https://httpbin.org/post",
                    "sendBody": True,
                    "contentType": "json",
                    "bodyParameters": {
                        "parameters": [
                            {"name": "channel", "value": "vip-hot-leads"},
                            {"name": "alert", "value": "={{ '🔥 HOT VIP LEAD: ' + $json.full_name + ' (' + $json.company + ') - Score: ' + $json.qualification.lead_score + '/100' }}"},
                            {"name": "pitch", "value": "={{ $json.qualification.suggested_pitch }}"}
                        ]
                    }
                }
            },
            {
                "id": vip_resp_id,
                "name": "VIP Webhook Response",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1460, 180],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={{ JSON.stringify({ status: 'success', priority: 'VIP_HOT', sla: '5m', message: 'VIP Lead queued for immediate executive concierge call.', lead_id: $('Normalize Lead Payload').item.json.lead_id, score: $('AI Lead Qualification & Scoring').item.json.qualification.lead_score }) }}",
                    "options": {"responseCode": 200}
                }
            },
            {
                "id": nurture_id,
                "name": "Standard Queue Logging",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1220, 420],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": """return {
  json: {
    status: "queued_for_nurture",
    lead_id: $json.lead_id,
    email: $json.email,
    score: $json.qualification.lead_score,
    action: "Added to GoHighLevel 7-Day Nurture Drip Campaign"
  }
};"""
                }
            },
            {
                "id": nurture_resp_id,
                "name": "Standard Webhook Response",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1460, 420],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={{ JSON.stringify({ status: 'success', priority: 'STANDARD', sla: '60m', message: 'Lead recorded and scheduled for nurture sequence.', lead_id: $json.lead_id, score: $json.score }) }}",
                    "options": {"responseCode": 200}
                }
            }
        ],
        "connections": {
            "GHL Webhook Ingest": {
                "main": [
                    [
                        {"node": "Normalize Lead Payload", "type": "main", "index": 0}
                    ]
                ]
            },
            "Normalize Lead Payload": {
                "main": [
                    [
                        {"node": "AI Lead Qualification & Scoring", "type": "main", "index": 0}
                    ]
                ]
            },
            "AI Lead Qualification & Scoring": {
                "main": [
                    [
                        {"node": "Check Priority (Is VIP?)", "type": "main", "index": 0}
                    ]
                ]
            },
            "Check Priority (Is VIP?)": {
                "main": [
                    # Output index 0: True branch
                    [
                        {"node": "Dispatch Instant VIP Alert", "type": "main", "index": 0}
                    ],
                    # Output index 1: False branch
                    [
                        {"node": "Standard Queue Logging", "type": "main", "index": 0}
                    ]
                ]
            },
            "Dispatch Instant VIP Alert": {
                "main": [
                    [
                        {"node": "VIP Webhook Response", "type": "main", "index": 0}
                    ]
                ]
            },
            "Standard Queue Logging": {
                "main": [
                    [
                        {"node": "Standard Webhook Response", "type": "main", "index": 0}
                    ]
                ]
            }
        },
        "settings": {
            "executionOrder": "v1"
        }
    }

    try:
        created = await client.create_workflow(workflow_payload)
        print(f"Workflow Created Successfully!")
        print(f"ID: {created.id}")
        print(f"Name: {created.name}")
        print(f"Nodes Count: {len(created.nodes)}")
        print(f"URL: {config.base_url}/workflow/{created.id}")

        # Activate the workflow
        try:
            activated = await client.activate_workflow(created.id, active=True)
            print(f"Workflow Activated: {activated.active}")
        except Exception as act_err:
            print(f"Note on activation: {act_err}")

    except Exception as e:
        print(f"Error creating workflow: {e}")
        raise
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
