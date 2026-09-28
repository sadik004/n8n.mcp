#!/usr/bin/env python3
"""
Test the deployed GoHighLevel workflow live by sending real HTTP webhook requests.
"""

import httpx
import json

def test_ghl_leads():
    webhook_url = "http://localhost:5678/webhook/ghl-inbound-lead"
    
    vip_lead = {
        "first_name": "Alexander",
        "last_name": "Vance",
        "email": "alex@vancerealtygroup.com",
        "phone": "2025550198",
        "company_name": "Vance Realty Group",
        "monthly_revenue": 25000,
        "service_needed": "GoHighLevel AI Lead Engine"
    }

    standard_lead = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "johndoe123@gmail.com",
        "phone": "",
        "company_name": "Solo Freelancer",
        "monthly_revenue": 500,
        "service_needed": "Basic Automation"
    }

    client = httpx.Client(timeout=10.0)

    print("--- 1. Testing VIP Hot Lead Ingestion ---")
    resp_vip = client.post(webhook_url, json=vip_lead)
    print(f"Status Code: {resp_vip.status_code}")
    print(f"Response: {resp_vip.text}")

    print("\n--- 2. Testing Standard Nurture Lead Ingestion ---")
    resp_std = client.post(webhook_url, json=standard_lead)
    print(f"Status Code: {resp_std.status_code}")
    print(f"Response: {resp_std.text}")

if __name__ == "__main__":
    test_ghl_leads()
