#!/usr/bin/env python3
"""Solve the final captcha step of a wrapped link with a real browser.

The chain up to the last step is done over HTTP by the resolver script.
This one opens the resulting page in a real Chromium, waits for the
countdown, lets the captcha widget finish, clicks the button, and reads
the destination the page navigates to.

Usage: python3 gplinks_browser.py <pid/vid url> [cookie-header]
"""

import json
import os
import re
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def parse_cookies(raw, domain):
    out = []
    for part in raw.split("; "):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        out.append({"name": name, "value": value, "domain": domain, "path": "/"})
    return out


def main(argv):
    if len(argv) < 2:
        print("usage: gplinks_browser.py <url> [cookie-header]", file=sys.stderr)
        return 2
    url = argv[1]
    raw_cookie = argv[2] if len(argv) > 2 else ""
    domain = re.sub(r"^https?://([^/]+).*$", r"\1", url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage", "--start-maximized",
                  "--disable-http1", "--enable-http2"])
        context = browser.new_context(
            user_agent=UA, viewport={"width": 1366, "height": 900},
            locale="en-US", timezone_id="Asia/Dhaka")
        if raw_cookie:
            context.add_cookies(parse_cookies(raw_cookie, domain))
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        page = context.new_page()
        page.goto("https://%s/" % domain, referer=None,
                  wait_until="domcontentloaded")
        time.sleep(2)
        page.goto(url, referer="https://%s/" % domain,
                  wait_until="domcontentloaded")
        time.sleep(4)

        print("title:", page.title(), "| url:", page.url, file=sys.stderr)

        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                frame_ok = False
                for frame in page.frames:
                    if "challenges.cloudflare.com" in (frame.url or ""):
                        frame_ok = True
                widget = page.query_selector(".cf-turnstile")
                button = page.query_selector("#captchaButton")
                print("widget:", bool(widget), "| button:",
                      (button.inner_text() if button else None),
                      "| cf frame:", frame_ok, file=sys.stderr)
                if button and "wait" not in (button.inner_text() or "").lower():
                    button.click()
                    break
            except Exception as exc:
                print("poll:", str(exc)[:120], file=sys.stderr)
            time.sleep(2)

        time.sleep(6)
        print("after click url:", page.url, file=sys.stderr)

        destination = None
        for _ in range(40):
            if re.search(r"mediafire", page.url, re.I):
                destination = page.url
                break
            body = page.content()
            hit = re.search(r'https?://[^\s\'"<>)]*mediafire[^\s\'"<>)]*', body, re.I)
            if hit:
                destination = hit.group(0)
                break
            time.sleep(1)

        print(json.dumps({"url": page.url, "destination": destination}))
        browser.close()
    return 0 if destination else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
