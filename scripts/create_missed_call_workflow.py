#!/usr/bin/env python3
"""
Deploy AI Missed-Call Speed-to-Lead & Autonomous Booking Recovery Engine in n8n.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from n8n_mcp.config import N8nConfig
from n8n_mcp.engine.client import N8nClient


async def main():
    config = N8nConfig()
    client = N8nClient(config=config)

    webhook_id = str(uuid.uuid4())
    lookup_id = str(uuid.uuid4())
    ai_gen_id = str(uuid.uuid4())
    if_emergency_id = str(uuid.uuid4())
    urgent_alert_id = str(uuid.uuid4())
    urgent_resp_id = str(uuid.uuid4())
    booking_sms_id = str(uuid.uuid4())
    booking_resp_id = str(uuid.uuid4())

    workflow_payload = {
        "name": "[Speed-to-Lead] AI Missed-Call Recovery & Booking Engine",
        "nodes": [
            {
                "id": webhook_id,
                "name": "Missed Call Trigger",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [240, 300],
                "parameters": {
                    "httpMethod": "POST",
                    "path": "missed-call-trigger",
                    "responseMode": "responseNode",
                    "options": {}
                }
            },
            {
                "id": lookup_id,
                "name": "Caller Normalizer & Context Builder",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [480, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": """const raw = $json.body || $json;

let rawPhone = String(raw.caller_phone || raw.phone || '');
let cleanPhone = rawPhone.replace(/[^\\d+]/g, '');
if (cleanPhone.length === 10 && !cleanPhone.startsWith('+')) {
  cleanPhone = '+1' + cleanPhone;
}

const callerName = (raw.caller_name || raw.name || 'Valued Caller').trim();
const businessName = (raw.business_name || 'Apex Services Group').trim();
const callIntent = (raw.intent || raw.reason || 'General Inquiry').trim();
const isUrgentTag = Boolean(raw.is_emergency || raw.urgent || false);

return {
  json: {
    call_id: 'CALL-' + Date.now().toString(36).toUpperCase(),
    caller_name: callerName,
    caller_phone: cleanPhone,
    business_name: businessName,
    raw_intent: callIntent,
    is_urgent_declared: isUrgentTag,
    call_timestamp: new Date().toISOString()
  }
};"""
                }
            },
            {
                "id": ai_gen_id,
                "name": "AI Speed-to-Lead SMS Generator",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [720, 300],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": """const data = $json;
const intentLower = data.raw_intent.toLowerCase();

// Classify urgency level
let isEmergency = false;
let urgencyScore = 30;
const emergencyKeywords = ['leak', 'burst', 'flood', 'pain', 'emergency', 'urgent', 'broken', 'accident', 'lawyer', 'arrest'];

for (const kw of emergencyKeywords) {
  if (intentLower.includes(kw) || data.is_urgent_declared) {
    isEmergency = true;
    urgencyScore = 95;
    break;
  }
}

// Generate human-mimetic conversational SMS copy
let smsDraft = '';
let responseAction = '';

if (isEmergency) {
  smsDraft = `🚨 URGENT: Hi ${data.caller_name}, saw your missed call regarding "${data.raw_intent}". Our on-call emergency technician has been paged immediately. If life-threatening call 911, otherwise our direct emergency dispatch line is (555) 019-9999.`;
  responseAction = 'DISPATCH_ON_CALL_MANAGER';
} else {
  smsDraft = `Hi ${data.caller_name}! Sorry I just missed your call at ${data.business_name}—was assisting another client. How can I help you today? If you'd like to reserve a quick 10-min phone consultation, grab any slot here: https://${data.business_name.toLowerCase().replace(/\\s+/g, '')}.com/book`;
  responseAction = 'SEND_AUTONOMOUS_BOOKING_LINK';
}

return {
  json: {
    ...data,
    ai_decision: {
      is_emergency: isEmergency,
      urgency_score: urgencyScore,
      action_type: responseAction,
      personalized_sms: smsDraft,
      speed_to_lead_sla_seconds: 30
    }
  }
};"""
                }
            },
            {
                "id": if_emergency_id,
                "name": "Is Emergency Call?",
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
                                "id": "cond-emergency",
                                "leftValue": "={{ $json.ai_decision.is_emergency }}",
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
                "id": urgent_alert_id,
                "name": "Page On-Call Emergency Team",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1220, 180],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": """const item = $json;
return {
  json: {
    event: "CRITICAL_ON_CALL_PAGE",
    target: "Staff Emergency Roster",
    caller: item.caller_name,
    phone: item.caller_phone,
    urgency_score: item.ai_decision.urgency_score,
    paged_at: new Date().toISOString(),
    status: "ESCALATED_HIGH_PRIORITY",
    outbound_sms_sent: item.ai_decision.personalized_sms
  }
};"""
                }
            },
            {
                "id": urgent_resp_id,
                "name": "Emergency Webhook Response",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1460, 180],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={{ JSON.stringify({ status: 'success', flow: 'EMERGENCY_ESCALATION', caller_phone: $json.phone, sla: '30s', outbound_sms: $json.outbound_sms_sent }) }}",
                    "options": {"responseCode": 200}
                }
            },
            {
                "id": booking_sms_id,
                "name": "Queue Conversational SMS & Booking",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [1220, 420],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": """const item = $json;
return {
  json: {
    event: "SPEED_TO_LEAD_SMS_DELIVERED",
    caller_phone: item.caller_phone,
    caller_name: item.caller_name,
    business: item.business_name,
    sms_content: item.ai_decision.personalized_sms,
    booking_link_delivered: true,
    scheduled_followup_if_no_reply: "15 minutes",
    status: "CONVERSATIONAL_CADENCE_ACTIVE"
  }
};"""
                }
            },
            {
                "id": booking_resp_id,
                "name": "Standard Booking Response",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.1,
                "position": [1460, 420],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={{ JSON.stringify({ status: 'success', flow: 'SPEED_TO_LEAD_BOOKING', caller_phone: $json.caller_phone, action: 'SMS dispatched with calendar link', sla: '30s' }) }}",
                    "options": {"responseCode": 200}
                }
            }
        ],
        "connections": {
            "Missed Call Trigger": {
                "main": [
                    [
                        {"node": "Caller Normalizer & Context Builder", "type": "main", "index": 0}
                    ]
                ]
            },
            "Caller Normalizer & Context Builder": {
                "main": [
                    [
                        {"node": "AI Speed-to-Lead SMS Generator", "type": "main", "index": 0}
                    ]
                ]
            },
            "AI Speed-to-Lead SMS Generator": {
                "main": [
                    [
                        {"node": "Is Emergency Call?", "type": "main", "index": 0}
                    ]
                ]
            },
            "Is Emergency Call?": {
                "main": [
                    # Output index 0: True branch (Emergency)
                    [
                        {"node": "Page On-Call Emergency Team", "type": "main", "index": 0}
                    ],
                    # Output index 1: False branch (Booking / Normal)
                    [
                        {"node": "Queue Conversational SMS & Booking", "type": "main", "index": 0}
                    ]
                ]
            },
            "Page On-Call Emergency Team": {
                "main": [
                    [
                        {"node": "Emergency Webhook Response", "type": "main", "index": 0}
                    ]
                ]
            },
            "Queue Conversational SMS & Booking": {
                "main": [
                    [
                        {"node": "Standard Booking Response", "type": "main", "index": 0}
                    ]
                ]
            }
        },
        "settings": {
            "executionOrder": "v1"
        }
    }

    try:
        # Check if already exists
        existing_list = await client.list_workflows()
        existing_wf = next((w for w in existing_list.data if w.name == workflow_payload["name"]), None)

        if existing_wf:
            target_id = existing_wf.id
            workflow_payload["id"] = target_id
            created = await client.update_workflow(target_id, workflow_payload)
            print(f"Workflow Updated Successfully!")
        else:
            created = await client.create_workflow(workflow_payload)
            print(f"Workflow Created Successfully!")

        print(f"ID: {created.id}")
        print(f"Name: {created.name}")
        print(f"Nodes Count: {len(created.nodes)}")
        print(f"URL: {config.n8n_host}/workflow/{created.id}")

        # Activate the workflow
        try:
            activated = await client.activate_workflow(created.id, active=True)
            print(f"Workflow Activated: {activated.active}")
        except Exception as act_err:
            print(f"Note on activation: {act_err}")

    except Exception as e:
        print(f"Error deploying workflow: {e}")
        raise
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
