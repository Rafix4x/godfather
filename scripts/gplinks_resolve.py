#!/usr/bin/env python3
"""HTTP layer for the gated link chain.

The chain has three layers. The outer shortener serves a bot-check page
whose obfuscated script builds a verification form. Behind that sits a
subscription wall with a free path. Behind that sits a multi-step
content gate that the page's own script drives through a REST endpoint
that returns the final URL.

Every layer is driven the way the browser drives it: the page's own
check script is extracted and evaluated under a stubbed desktop
browser, the form it builds is submitted on the same connection, and the
cookies that come back are carried forward.

stdlib only, Python 3.9+. Requires node on PATH.
"""

import http.client
import json
import os
import re
import ssl
import subprocess
import sys
import time

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

HARNESS = r"""
const src = require('fs').readFileSync(process.argv[2], 'utf8');
let captured = null;
const elems = {};
function mkEl(tag) {
  const e = {
    tagName: tag, name: '', value: '', type: 'text', id: '', style: {},
    children: [], props: {},
    appendChild(c) { this.children.push(c); },
    setAttribute(k, v) { this.props[k] = v; },
    submit() { this.submitted = true; }
  };
  return e;
}
elems['rvc72havtanp'] = mkEl('div');
const doc = {
  createElement: mkEl,
  getElementById: (id) => elems[id] || null,
  addEventListener(ev, fn) { if (ev === 'DOMContentLoaded') doc.__ready = fn; },
  attachEvent() {},
  body: { appendChild(e) { elems[e.id] = e; } },
  readyState: 'loading'
};
global.document = doc;
function Plugin() {}
function MimeType() {}
global.Plugin = Plugin;
global.MimeType = MimeType;
global.PluginArray = {prototype: {}};
global.MimeTypeArray = {prototype: {}};
const plugins = Object.create(PluginArray.prototype);
plugins.length = 5;
for (let i = 0; i < 5; i++) plugins[i] = Object.create(Plugin.prototype);
const mimeTypes = Object.create(MimeTypeArray.prototype);
mimeTypes.length = 2;
for (let i = 0; i < 2; i++) mimeTypes[i] = Object.create(MimeType.prototype);
global.window = {
  navigator: {
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    appVersion: '5.0 (X11)', languages: ['en-US', 'en'], language: 'en-US',
    plugins: plugins, mimeTypes: mimeTypes, webdriver: undefined
  },
  outerWidth: 1280, outerHeight: 900, document: doc,
  location: {reload() {}},
  addEventListener(ev, fn) { if (ev === 'DOMContentLoaded') doc.__ready = fn; }
};
global.XMLHttpRequest = function() {
  this.open = (...a) => { captured = {url: a[1], method: a[0]}; };
  this.send = () => {};
};
try { (0, eval)(src); } catch (e) { console.log('EVALERR ' + e.message); }
if (doc.__ready) { try { doc.__ready(); } catch (e) { console.log('READYERR ' + e.message); } }
setTimeout(() => {
  const container = elems['rvc72havtanp'];
  const form = (container.children || []).find(c => c.tagName === 'form');
  const flat = {};
  (function walk(n) {
    if (!n) return;
    if (n.name) flat[n.name] = n.value;
    (n.children || []).forEach(walk);
  })(form);
  if (form) {
    console.log(JSON.stringify({
      mode: 'form', action: form.action, method: form.method, fields: flat
    }));
  } else if (captured) {
    console.log(JSON.stringify({mode: 'xhr', url: captured.url, method: captured.method}));
  } else {
    console.log(JSON.stringify({mode: 'none'}));
  }
}, 1600);
"""

FREE_VARIANTS = ("?skip_sub=1", "?skip=1", "?free=1")


def header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def connect(host):
    ctx = ssl.create_default_context()
    return http.client.HTTPSConnection(host, 443, timeout=25, context=ctx)


def request(conn, method, path, referer=None, cookie=None, payload=None,
            extra=None):
    headers = {"User-Agent": UA,
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "en-US,en;q=0.9"}
    if referer:
        headers["Referer"] = referer
    if cookie:
        headers["Cookie"] = cookie
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["X-Requested-With"] = "XMLHttpRequest"
    if extra:
        headers.update(extra)
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    text = resp.read().decode("utf-8", "replace")
    return resp.status, dict(resp.getheaders()), text


def add_cookies(cookie, headers):
    raw = header(headers, "Set-Cookie")
    if not raw:
        return cookie
    for part in raw.split(","):
        kv = part.split(";")[0].strip()
        if "=" in kv and kv.split("=")[0] not in (cookie or ""):
            cookie = ((cookie or "") + "; " + kv).strip("; ")
    return cookie


def run_form(html, workdir):
    scripts = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))
    match = re.search(
        r"(var a0I=a0v;[\s\S]*?function a0m\(\)\{var u=\[[\s\S]*?return a0m\(\);\})",
        scripts)
    if not match:
        return None
    chal = os.path.join(workdir, "challenge.js")
    harness = os.path.join(workdir, "harness.js")
    with open(chal, "w", encoding="utf-8") as handle:
        handle.write(match.group(1))
    with open(harness, "w", encoding="utf-8") as handle:
        handle.write(HARNESS)
    proc = subprocess.run(["node", harness, chal], capture_output=True,
                          text=True, timeout=40)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def challenge_page(host, path, workdir, tries=25):
    conn = connect(host)
    for _ in range(tries):
        status, headers, html = request(conn, "GET", path)
        if status == 200 and "a0I=a0v" in html:
            return conn, html
        conn.close()
        time.sleep(0.8)
        conn = connect(host)
    return conn, None


def unlock(host, path, referer, workdir):
    conn, html = challenge_page(host, path, workdir)
    if not html:
        return None
    result = run_form(html, workdir)
    if not result or result.get("mode") != "form":
        return None
    query = "&".join("%s=%s" % (k, v) for k, v in result["fields"].items())
    status, headers, body = request(conn, "GET", result["action"] + "?" + query,
                                    referer=referer)
    cookie = (header(headers, "Set-Cookie") or "").split(";")[0]
    if status in (301, 302, 303, 307, 308) and cookie:
        return conn, cookie
    return None


def gpf_advance(host, page_html, cookie, workdir, steps=6):
    """Drive the multi-step content gate the way the page's script does."""
    match = re.search(r'var gpfConfig = (\{.*?\});', page_html, re.S)
    if not match:
        return None
    try:
        config = json.loads(match.group(1))
    except ValueError:
        return None
    rest = config.get("rest")
    nonce = config.get("nonce")
    if not rest or not nonce:
        return None
    path = rest[len("https://%s" % host):] if rest.startswith("https://%s" % host) else rest
    conn = connect(host)
    for _ in range(steps):
        status, headers, body = request(
            conn, "POST", path + "advance", referer="https://%s/" % host,
            cookie=cookie, payload={"imps": 1},
            extra={"X-WP-Nonce": nonce})
        cookie = add_cookies(cookie, headers)
        try:
            data = json.loads(body)
        except ValueError:
            return None
        state = data.get("status")
        if state in ("next", "complete"):
            return {"url": data.get("url"), "cookie": cookie, "conn": conn}
        if state in ("expired", "no_session"):
            return None
        time.sleep(float(data.get("seconds") or 5))
    return None


