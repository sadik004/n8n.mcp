"""Automated Setup and Key Provisioning Wizard for n8n-mcp.

Helps developers set up native n8n (via npx), log in, and auto-provision
a Public REST API Key directly into .env and MCP configuration files.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent


def update_env_file(api_key: str, host: str = "http://localhost:5678") -> None:
    """Writes configured host and API key to local .env file."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        example_path = REPO_ROOT / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env_path.write_text("N8N_HOST=http://localhost:5678\nN8N_API_KEY=\n", encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated_host = False
    updated_key = False
    new_lines = []

    for line in lines:
        if line.startswith("N8N_HOST="):
            new_lines.append(f"N8N_HOST={host.rstrip('/')}")
            updated_host = True
        elif line.startswith("N8N_API_KEY="):
            new_lines.append(f"N8N_API_KEY={api_key}")
            updated_key = True
        else:
            new_lines.append(line)

    if not updated_host:
        new_lines.append(f"N8N_HOST={host.rstrip('/')}")
    if not updated_key:
        new_lines.append(f"N8N_API_KEY={api_key}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[+] Updated {env_path} successfully.")


async def auto_provision_playwright(
    target_url: str = "http://localhost:5678",
    email: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = False,
    timeout_seconds: int = 180,
) -> bool:
    """Uses Playwright to log in and generate an API key."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[-] Playwright is not installed. Install via: pip install playwright && playwright install chromium", file=sys.stderr)
        return False

    print(f"[*] Connecting to {target_url} using Playwright (headless={headless})...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            signin_url = f"{target_url.rstrip('/')}/signin"
            await page.goto(signin_url, wait_until="domcontentloaded", timeout=30000)

            email_input = page.locator("#emailOrLdapLoginId, input[name='emailOrLdapLoginId']")
            if await email_input.is_visible():
                if email and password:
                    print("[*] Entering credentials automatically...")
                    await email_input.fill(email)
                    pwd_input = page.locator("#password, input[name='password']")
                    await pwd_input.fill(password)
                    await page.get_by_role("button", name="Sign in").click()
                else:
                    print("[*] Please log in via the opened browser window...")

            # Wait for successful sign-in
            await page.wait_for_function(
                "() => !window.location.pathname.includes('/signin') && !window.location.pathname.includes('/setup')",
                timeout=timeout_seconds * 1000,
            )
            print("[+] Authenticated successfully.")

            # Dismiss any dialogs
            for _ in range(3):
                await page.keyboard.press("Escape")
                try:
                    close_btn = page.locator("button.el-dialog__headerbtn, button[aria-label='Close'], button:has-text('✕')").first
                    if await close_btn.is_visible():
                        await close_btn.click()
                except Exception:
                    pass

            # Go to API settings
            api_url = f"{target_url.rstrip('/')}/settings/api"
            await page.goto(api_url, wait_until="domcontentloaded", timeout=20000)
            await page.keyboard.press("Escape")

            # Click Create API Key
            create_btn = page.locator("button:has-text('Create an API key'), button:has-text('Create API key'), button:has-text('Create key')").first
            await create_btn.wait_for(state="visible", timeout=12000)
            await create_btn.click()

            dialog = page.locator("[role='dialog'], .el-dialog, #app-modals").first
            label_input = dialog.locator("input:not([readonly])").first
            await label_input.fill("n8n-mcp-key")
            await label_input.press("Enter")

            # Click Save/Create
            save_btn = dialog.locator("button:has-text('Create'), button:has-text('Save')").first
            if await save_btn.is_visible():
                await save_btn.click(force=True)

            await page.wait_for_timeout(1000)

            # Retrieve generated key
            for el in await page.locator("input[readonly], code, pre, .key-display").all():
                val = await el.input_value() if await el.evaluate("e => 'value' in e") else await el.inner_text()
                val = val.strip()
                if val.startswith("eyJ") or len(val) > 20:
                    print(f"[+] Retrieved API key: {val[:8]}...{val[-6:]}")
                    update_env_file(val, target_url)
                    return True

            print("[-] Could not automatically capture the generated key from modal.")
            return False

        except Exception as e:
            print(f"[-] Automated setup encountered an error: {e}", file=sys.stderr)
            return False
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="n8n-mcp Automated Setup and Configuration")
    parser.add_argument("--host", default="http://localhost:5678", help="n8n instance host URL")
    parser.add_argument("--key", default="", help="Existing n8n Public REST API key to save")
    parser.add_argument("--email", default="", help="n8n user login email")
    parser.add_argument("--password", default="", help="n8n user login password")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    args = parser.parse_args()

    if args.key:
        update_env_file(args.key, args.host)
        print("[+] Setup completed via provided API key.")
        return

    print("==================================================")
    print("        n8n-mcp Automated Setup Wizard            ")
    print("==================================================")
    print("1. If n8n is not running, launch it in another shell via:")
    print("   npx -y n8n")
    print("2. Starting automated browser provisioning...")

    success = asyncio.run(
        auto_provision_playwright(
            target_url=args.host,
            email=args.email,
            password=args.password,
            headless=args.headless,
        )
    )

    if not success:
        print("\n[*] You can also manually create an API key in n8n (Settings -> Public API)")
        manual_key = input("Enter your n8n Public API key: ").strip()
        if manual_key:
            update_env_file(manual_key, args.host)
            print("[+] Setup completed manually.")
        else:
            print("[-] No key provided. Setup aborted.")
            sys.exit(1)


if __name__ == "__main__":
    main()
