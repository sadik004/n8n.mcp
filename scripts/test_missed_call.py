#!/usr/bin/env python3
"""
Test the AI Missed-Call Speed-to-Lead workflow with real mock call events.
"""

import httpx
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def test_missed_calls():
    webhook_url = "http://localhost:5678/webhook/missed-call-trigger"
    client = httpx.Client(timeout=10.0)

    # Test Case 1: Standard Missed Call (General Consultation inquiry)
    normal_call = {
        "caller_name": "Sarah Jenkins",
        "caller_phone": "4155550143",
        "business_name": "SmileBright Dental Studio",
        "intent": "Inquiry about teeth whitening and routine checkup",
        "is_emergency": False
    }

    # Test Case 2: Emergency Missed Call (Burst pipe / flooding)
    emergency_call = {
        "caller_name": "Robert Miller",
        "caller_phone": "2125550188",
        "business_name": "Apex Emergency Plumbing",
        "intent": "Major pipe burst under sink, kitchen is flooding!",
        "is_emergency": True
    }

    print("--- 1. Testing Standard Missed Call (Booking Link Flow) ---")
    resp_normal = client.post(webhook_url, json=normal_call)
    print(f"Status Code: {resp_normal.status_code}")
    print(f"Response: {resp_normal.text}")

    print("\n--- 2. Testing Emergency Missed Call (Instant Dispatch Flow) ---")
    resp_emerg = client.post(webhook_url, json=emergency_call)
    print(f"Status Code: {resp_emerg.status_code}")
    print(f"Response: {resp_emerg.text}")

if __name__ == "__main__":
    test_missed_calls()
