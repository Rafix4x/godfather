#!/usr/bin/env python3
"""Resolve a wrapped link chain down to the real destination.

The chain has three stages.

1. The shortener serves a bot-check page whose obfuscated script builds
   a verification form. The script is evaluated under a stubbed desktop
   browser, the form it builds is submitted, and the splash cookie comes
   back.
2. The subscription wall is skipped through its free query parameter,
   which hands over the next host.
3. The next site runs a multi-step content gate driven through a REST
   endpoint. Each step answers with the next page; the last one answers
   with the shortener again.
4. The shortener's last page carries a captcha widget, which is solved
   in a real browser, and the token it produces is posted back to get
   the destination.

The edge in front of these hosts refuses a headless browser's own
request, so the browser's document requests carry the referer the edge
expects.

Usage: python3 gplinks_chain.py <url>
"""

import contextlib
import importlib.util
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "gplinks_http", os.path.join(HERE, "gplinks_resolve.py"))
HTTP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(HTTP)

PATCH = r"""
(function () {
  try {
    Object.defineProperty(Navigator.prototype, 'webdriver',
      {get: function () { return undefined; }, configurable: true});
  } catch (e) {}
  try {
    function Plugin() {}
    function MimeType() {}
    window.Plugin = Plugin;
    window.MimeType = MimeType;
    window.PluginArray = {prototype: {}};
    window.MimeTypeArray = {prototype: {}};
    var plugins = Object.create(window.PluginArray.prototype);
    plugins.length = 5;
    for (var i = 0; i < 5; i++) { plugins[i] = Object.create(Plugin.prototype); }
    var mimeTypes = Object.create(window.MimeTypeArray.prototype);
    mimeTypes.length = 2;
    for (var j = 0; j < 2; j++) { mimeTypes[j] = Object.create(MimeType.prototype); }
    Object.defineProperty(Navigator.prototype, 'plugins',
      {get: function () { return plugins; }, configurable: true});
    Object.defineProperty(Navigator.prototype, 'mimeTypes',
      {get: function () { return mimeTypes; }, configurable: true});
    Object.defineProperty(Navigator.prototype, 'languages',
      {get: function () { return ['en-US', 'en']; }, configurable: true});
    Object.defineProperty(Navigator.prototype, 'language',
      {get: function () { return 'en-US'; }, configurable: true});
  } catch (e) {}
})();
"""

SOLVE_CHECK = """
async () => {
  const container = document.getElementById('rvc72havtanp');
  if (!container) { return {status: 'no-container'}; }
  const form = container.querySelector('form');
  if (!form) { return {status: 'no-form'}; }
  const action = form.getAttribute('action');
  const method = (form.getAttribute('method') || 'GET').toUpperCase();
  const data = new URLSearchParams();
  form.querySelectorAll('input').forEach(function (i) {
    if (i.name) { data.append(i.name, i.value); }
  });
  const url = action + (action.indexOf('?') === -1 ? '?' : '&') + data.toString();
  const resp = await fetch(url, {method: method, credentials: 'same-origin'});
  return {status: 'submitted', code: resp.status};
}
"""


def say(message):
    print(message, file=sys.stderr, flush=True)


def split(url):
    host = re.match(r"https?://([^/]+)", url).group(1)
    path = re.match(r"https?://[^/]+(/.*)?$", url).group(1) or "/"
    return host, path


class Host(object):
    """One connection and one cookie jar for a single host."""

    def __init__(self, host):
        self.host = host
        self.conn = HTTP.connect(host)
        self.cookie = ""

    def get(self, path, referer=None):
        status, headers, body = HTTP.request(self.conn, "GET", path,
                                             referer=referer, cookie=self.cookie)
        self.cookie = HTTP.add_cookies(self.cookie, headers)
        return status, headers, body

    def post(self, path, referer, payload, extra=None):
        status, headers, body = HTTP.request(self.conn, "POST", path,
                                             referer=referer, cookie=self.cookie,
                                             payload=payload, extra=extra)
        self.cookie = HTTP.add_cookies(self.cookie, headers)
        return status, headers, body

    def reopen(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = HTTP.connect(self.host)

    def pass_check(self, path, referer, workdir, tries=30):
        """Pass the bot check so the session cookie is live.

        The edge in front of these hosts answers some addresses with a
        refusal, so a fresh connection is opened on every refusal.
        """
        for _ in range(tries):
            status, headers, page = self.get(path, referer=referer)
            if status != 200:
                self.reopen()
                time.sleep(0.8)
                continue
            if "a0I=a0v" in page:
                result = HTTP.run_form(page, workdir)
                if result and result.get("mode") == "form":
                    query = "&".join("%s=%s" % (k, v)
                                     for k, v in result["fields"].items())
                    status, headers, body = self.get(result["action"] + "?" + query,
                                                     referer=referer)
                    if status in (301, 302, 303, 307, 308):
                        return True
            time.sleep(0.8)
        return False


def run_gate(site, page, referer):
    """Drive the multi-step content gate. Returns the final URL."""
    for _ in range(24):
        match = re.search(r'var gpfConfig = (\{.*?\});', page, re.S)
        if not match:
            return None
        config = json.loads(match.group(1))
        nonce = config.get("nonce")
        rest = config.get("rest") or ""
        path = rest[len("https://%s" % site.host):] if rest.startswith("https://%s" % site.host) else rest
        if not path:
            return None
        for _ in range(15):
            status, headers, body = site.post(path + "advance", referer,
                                              {"imps": 1},
                                              extra={"X-WP-Nonce": nonce})
            try:
                data = json.loads(body)
            except ValueError:
                return None
            state = data.get("status")
            say("  advance: " + str(state))
            if state in ("next", "complete"):
                nxt = data.get("url")
                if not nxt:
                    return None
                if site.host not in nxt:
                    return nxt
                status, headers, page = site.get(
                    nxt.replace("https://%s" % site.host, "") or "/", referer=nxt)
                referer = nxt
                break
            if state in ("expired", "no_session"):
                return None
            time.sleep(float(data.get("seconds") or 5))
        else:
            return None
    return None


BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# the edge refuses the browser's own document request: it checks the
# user agent against the client hints it sends, and it refuses a request
# that carries the browser's compression and client hint headers
BROWSER_STRIP = ("accept-encoding", "sec-ch-ua", "sec-ch-ua-mobile",
                  "sec-ch-ua-platform", "sec-ch-ua-platform-version",
                  "sec-ch-ua-full-version-list", "sec-ch-ua-arch",
                  "sec-ch-ua-model", "upgrade-insecure-requests")


@contextlib.contextmanager
def browser_session(url, referer, cookie=None, host=None):
    """Open a browser on the shortener with the referer the edge expects.

    The record that the content gate handed over belongs to the session
    that started the chain, so that session's cookies are put into the
    browser before it opens the page.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        say("playwright is not installed: pip install playwright && playwright install chromium")
        yield None, None, None
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-gpu"])
        context = browser.new_context(viewport={"width": 1366, "height": 900},
                                       locale="en-US", user_agent=BROWSER_UA)
        context.add_init_script(PATCH)
        if cookie and host:
            jar = []
            for part in cookie.split(";"):
                if "=" not in part:
                    continue
                name, value = part.strip().split("=", 1)
                jar.append({"name": name, "value": value, "domain": host,
                            "path": "/"})
            if jar:
                context.add_cookies(jar)
                say("  browser cookies: " + ", ".join(c["name"] for c in jar))
        page = context.new_page()

        def fix(route):
            headers = dict(route.request.headers)
            if route.request.resource_type == "document":
                headers["Referer"] = referer
                headers["Sec-Fetch-Site"] = "same-origin"
                for name in BROWSER_STRIP:
                    headers.pop(name, None)
            route.continue_(headers=headers)

        page.route("**/*", fix)

        def open_page():
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
            except Exception as exc:
                say("nav: " + str(exc)[:100])

        open_page()
        # the edge turns a first visit away now and then, so the page is
        # opened again until it stays
        for attempt in range(8):
            try:
                title = page.title()
                widgets = page.evaluate(
                    "() => document.querySelectorAll('.cf-turnstile').length")
            except Exception:
                title, widgets = "", 0
            if "403" not in title and widgets:
                break
            say("  browser visit %d: %s" % (attempt, (title or "no title")[:40]))
            time.sleep(3)
            open_page()
        try:
            yield browser, context, page
        finally:
            try:
                browser.close()
            except Exception:
                pass


def has(page, selector):
    try:
        return bool(page.query_selector(selector))
    except Exception:
        return False


def solve_check(page, rounds=25):
    """Let the page's own check build its form and submit it."""
    for _ in range(rounds):
        try:
            if has(page, "#rvc72havtanp form"):
                result = page.evaluate(SOLVE_CHECK)
                say("  check submitted: " + json.dumps(result)[:120])
                return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


def solve_captcha(page, rounds=70):
    """Wait for the widget and click it if it asks."""
    clicked = False
    for attempt in range(rounds):
        try:
            token = page.evaluate("""() => {
              const el = document.querySelector('input[name="cf-turnstile-response"]')
                     || document.querySelector('textarea[name="cf-turnstile-response"]')
                     || document.querySelector('input[name="g-recaptcha-response"]');
              return el ? el.value : null;
            }""")
        except Exception:
            token = None
        if token:
            return token
        if attempt == 2:
            try:
                say("  page: " + page.title()[:60] + " | widgets: " +
                    str(page.evaluate("() => document.querySelectorAll('.cf-turnstile').length")) +
                    " | frames: " + str([f.url[:50] for f in page.frames]))
            except Exception as exc:
                say("  page state: " + str(exc)[:80])
        if not clicked:
            for frame in page.frames:
                if "challenges.cloudflare.com" not in (frame.url or ""):
                    continue
                try:
                    box = frame.locator("input[type=checkbox]").first
                    if box.count():
                        box.click(timeout=5000)
                        say("  clicked the widget")
                        clicked = True
                except Exception:
                    pass
                break
        time.sleep(2)
    return None


def post_go(site, url, page_html, token):
    """Post the captcha form and read the destination out of the answer."""
    match = re.search(r'<form method="post"[^>]*id="go-link".*?</form>', page_html, re.S)
    if not match:
        return None
    fields = {}
    for tag in re.findall(r'<input\b[^>]*>', match.group(0)):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = value.group(1) if value else ""
    if token:
        fields["cf-turnstile-response"] = token
        fields["g-recaptcha-response"] = token
    status, headers, text = site.post("/links/go", url, fields)
    say("links/go: " + str(status) + " " + text[:200])
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data.get("url")


def resolve(url, workdir="/tmp/gplinks"):
    if "://" not in url:
        url = "https://" + url
    host, path = split(url)
    say("shortener: " + url)

    shortener = Host(host)
    if not shortener.pass_check(path, url, workdir):
        say("could not pass the bot check")
        return None

    status, headers, body = shortener.get(path, referer=url)
    location = HTTP.header(headers, "Location")
    if location and host in location:
        path = re.match(r"https?://[^/]+(/.*)?$", location).group(1) or "/"
    found = None
    for candidate in HTTP.FREE_VARIANTS:
        status, headers, body = shortener.get(path + candidate, referer=url)
        location = HTTP.header(headers, "Location")
        if location and host not in location:
            found = location
            break
    if not found:
        say("the wall did not hand over the next host")
        return None
    say("wall skipped -> " + found)

    site_host, site_path = split(found)
    site = Host(site_host)
    if not site.pass_check(site_path, found, workdir):
        say("could not pass the bot check on the second host")
        return None
    status, headers, page = site.get(site_path, referer=found)
    location = HTTP.header(headers, "Location")
    if location and site_host in location:
        site_path = re.match(r"https?://[^/]+(/.*)?$", location).group(1) or "/"
        status, headers, page = site.get(site_path, referer=found)
    if "gpfConfig" not in (page or ""):
        say("no content gate on the second host")
        return None
    last = run_gate(site, page, found)
    if not last:
        say("the content gate did not finish")
        return None
    say("gate finished -> " + last)

    # the captcha page, on the shortener's own session
    host, path = split(last)
    status, headers, page_html = shortener.get(path, referer=last)
    if 'id="go-link"' not in (page_html or ""):
        status, headers, page_html = shortener.get(path, referer=last)
    if 'id="go-link"' not in (page_html or ""):
        say("the captcha page did not load")
        return None
    say("captcha page: " + last)
    try:
        import json as _json
        open("/tmp/gp_chain_state.json", "w").write(
            _json.dumps({"cookie": shortener.cookie, "url": last}))
    except Exception:
        pass

    with browser_session(last, last, cookie=shortener.cookie, host=host) as session:
        browser, context, page = session
        token = solve_captcha(page)
        if not token:
            say("the captcha was not solved")
            return None
        say("captcha token: yes")
        return post_go(shortener, last, page_html, token)


def main(argv):
    if len(argv) < 2:
        print("usage: gplinks_chain.py <url>", file=sys.stderr)
        return 2
    target = resolve(argv[1])
    if not target:
        print("error: no destination found", file=sys.stderr)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
