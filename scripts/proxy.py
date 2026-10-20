"""
proxy — a local endpoint that sits between an agent and its model provider.

An agent that talks to this endpoint sees an ordinary API. Behind it, the
request goes through the same ladder the relay uses: the model family
payload, the framing modes, the sibling models, and the refusal cleaner. A
refusal never reaches the agent, because the response is rebuilt before it
is sent back.

The agent only has to be pointed at this endpoint. The provider key, the
model and the base URL all come from the agent's own configuration, so the
proxy changes where the request goes, not who pays for it.

    python3 proxy.py --port 8787 --agent codex

Then point the agent at it:

    Codex      base_url = "http://127.0.0.1:8787/v1"
    Claude     ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"
    OpenAI     base_url = "http://127.0.0.1:8787/v1"

The upstream call is made in one shot and the reply is wrapped as a stream
when the caller asked for one, so a streaming agent keeps working.
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provider_resolve
import relay as relay_lib
import payloads as payload_lib

STATE = {"requests": 0, "refusals": 0, "recovered": 0, "models": []}
LOCK = threading.Lock()
CONFIG = {"agent": None, "timeout": 180, "max_tokens": 8000, "frames": None,
          "provider_scan": False, "system": None}


def load_godmode_env():
    path = os.path.join(os.path.expanduser("~"), ".godmode", "env")
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def extract_text(payload, transport):
    if transport == "anthropic":
        blocks = payload.get("messages") or []
        system = payload.get("system")
        if isinstance(system, str) and system:
            blocks = [{"role": "system", "content": system}] + blocks
        parts = []
        for message in blocks:
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text") or "")
                    elif isinstance(block, dict) and block.get("text"):
                        parts.append(block["text"])
        return "\n".join(p for p in parts if p)
    messages = payload.get("messages") or []
    if payload.get("system"):
        messages = [{"role": "system", "content": payload["system"]}] + messages
    parts = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text") or "")
    return "\n".join(p for p in parts if p)


def split_system(payload, transport):
    if transport == "anthropic":
        system = payload.get("system")
        if isinstance(system, list):
            system = "\n".join(b.get("text", "") for b in system
                               if isinstance(b, dict))
        return system or "", payload.get("messages") or []
    messages = list(payload.get("messages") or [])
    system = ""
    kept = []
    for message in messages:
        if message.get("role") == "system":
            content = message.get("content")
            if isinstance(content, str):
                system += content + "\n"
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("text"):
                        system += block["text"] + "\n"
        else:
            kept.append(message)
    return system.strip(), kept


def resolve_upstream(model_hint=None):
    cands = provider_resolve.resolve(CONFIG["agent"])
    if not cands:
        return None, None
    if model_hint:
        for cand in cands:
            if model_hint in (cand.get("model") or "",
                              cand.get("extra_models") or []):
                return cand, model_hint
        for cand in cands:
            return cand, model_hint
    cand = cands[0]
    return cand, cand.get("model")




def ladder_args(prompt):
    args = argparse.Namespace()
    args.prompt = prompt
    args.agent = CONFIG["agent"]
    args.provider_scan = CONFIG["provider_scan"]
    args.max_providers = 6
    args.max_models = 12
    args.max_tokens = CONFIG["max_tokens"]
    args.timeout = CONFIG["timeout"]
    args.transport = None
    args.base_url = None
    args.api_key = None
    args.model = None
    args.no_payloads = False
    args.no_obfuscation = False
    args.frame = CONFIG["frames"][0] if CONFIG["frames"] else None
    args.system = CONFIG["system"]
    args.system_file = None
    args.quiet = True
    args.json = False
    args.retries = 1
    return args


def run_ladder(cand, model, prompt, system):
    args = ladder_args(prompt)
    if system:
        args.system = system
    status, attempts, used_cand, used_model, frame, rec = relay_lib.run(args)
    if rec and rec.get("ok"):
        with LOCK:
            STATE["recovered"] += 1
            STATE["models"].append("%s | %s" % (used_model, frame))
        return rec, attempts
    return None, attempts


def response_text(payload, transport):
    try:
        if transport == "anthropic":
            for block in payload.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text") or ""
            return ""
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(b.get("text", "") for b in content
                           if isinstance(b, dict))
        return ""
    except (AttributeError, TypeError, IndexError):
        return ""


def openai_reply(text, model, usage=None):
    return {
        "id": "chatcmpl-godfather",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0,
                           "total_tokens": 0},
    }


def anthropic_reply(text, model):
    return {
        "id": "msg_godfather",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def stream_openai(text, model):
    chunk = {
        "id": "chatcmpl-godfather",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"},
                     "finish_reason": None}],
    }
    yield "data: " + json.dumps(chunk) + "\n\n"
    piece = {
        "id": "chatcmpl-godfather",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": text},
                     "finish_reason": None}],
    }
    yield "data: " + json.dumps(piece) + "\n\n"
    last = {
        "id": "chatcmpl-godfather",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield "data: " + json.dumps(last) + "\n\n"
    yield "data: [DONE]\n\n"


def stream_anthropic(text, model):
    start = {
        "type": "message_start",
        "message": {
            "id": "msg_godfather", "type": "message", "role": "assistant",
            "model": model, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    }
    yield "event: message_start\ndata: " + json.dumps(start) + "\n\n"
    opened = {
        "type": "content_block_start", "index": 0,
        "content_block": {"type": "text", "text": ""},
    }
    yield "event: content_block_start\ndata: " + json.dumps(opened) + "\n\n"
    delta = {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": text}}
    yield "event: content_block_delta\ndata: " + json.dumps(delta) + "\n\n"
    stop = {"type": "content_block_stop", "index": 0}
    yield "event: content_block_stop\ndata: " + json.dumps(stop) + "\n\n"
    end = {"type": "message_delta",
           "delta": {"stop_reason": "end_turn", "stop_sequence": None},
           "usage": {"output_tokens": 0}}
    yield "event: message_delta\ndata: " + json.dumps(end) + "\n\n"
    done = {"type": "message_stop"}
    yield "event: message_stop\ndata: " + json.dumps(done) + "\n\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "godfather-proxy/1.0"

    def log_message(self, format, *args):
        if os.environ.get("GODFATHER_PROXY_VERBOSE"):
            sys.stderr.write("[proxy] " + (format % args) + "\n")

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message, status=502):
        self._send_json({"error": {"message": message, "type": "godfather"}},
                        status)

    def _send_stream(self, chunks):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        try:
            for chunk in chunks:
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/v1/health", ""):
            self._send_json({"status": "ok", "requests": STATE["requests"],
                             "refusals": STATE["refusals"],
                             "recovered": STATE["recovered"]})
            return
        if self.path.rstrip("/") in ("/models", "/v1/models"):
            self._send_json({"object": "list",
                             "data": [{"id": m, "object": "model",
                                       "owned_by": "godfather"}
                                      for m in STATE["models"][-50:]]})
            return
        self._send_error("not found", 404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/chat/completions"):
            self._handle_openai()
            return
        if path.endswith("/messages"):
            self._handle_anthropic()
            return
        if path.endswith("/completions"):
            self._handle_openai()
            return
        self._send_error("not found", 404)

    def _handle_openai(self):
        payload = self._read_body()
        with LOCK:
            STATE["requests"] += 1
        model_hint = payload.get("model")
        system, messages = split_system(payload, "openai")
        prompt = extract_text({"messages": messages}, "openai")
        if not prompt.strip():
            self._send_json(openai_reply("", model_hint or "godfather"))
            return
        cand, model = resolve_upstream(model_hint)
        if not cand:
            self._send_error("no provider resolved", 502)
            return
        rec, attempts = run_ladder(cand, model, prompt, system)
        if rec is None:
            with LOCK:
                STATE["refusals"] += 1
            self._send_error("every attempt was refused", 502)
            return
        text = rec.get("content") or ""
        model = rec.get("model") or model
        if payload.get("stream"):
            self._send_stream(stream_openai(text, model))
            return
        self._send_json(openai_reply(text, model, rec.get("usage")))

    def _handle_anthropic(self):
        payload = self._read_body()
        with LOCK:
            STATE["requests"] += 1
        model_hint = payload.get("model")
        system, messages = split_system(payload, "anthropic")
        prompt = extract_text({"messages": messages}, "anthropic")
        if not prompt.strip():
            self._send_json(anthropic_reply("", model_hint or "godfather"))
            return
        cand, model = resolve_upstream(model_hint)
        if not cand:
            self._send_error("no provider resolved", 502)
            return
        rec, attempts = run_ladder(cand, model, prompt, system)
        if rec is None:
            with LOCK:
                STATE["refusals"] += 1
            self._send_error("every attempt was refused", 502)
            return
        text = rec.get("content") or ""
        model = rec.get("model") or model
        if payload.get("stream"):
            self._send_stream(stream_anthropic(text, model))
            return
        self._send_json(anthropic_reply(text, model))


def main(argv=None):
    ap = argparse.ArgumentParser(description="godfather local proxy")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--agent", default=None,
                    help="resolve this agent's provider")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--frame", default=None,
                    help="use one framing mode instead of the whole ladder")
    ap.add_argument("--provider-scan", action="store_true")
    ap.add_argument("--system", default=None)
    ap.add_argument("--print-env", action="store_true",
                    help="print the variables to export, then exit")
    args = ap.parse_args(argv)

    load_godmode_env()
    CONFIG["agent"] = args.agent
    CONFIG["timeout"] = args.timeout
    CONFIG["max_tokens"] = args.max_tokens
    CONFIG["frames"] = [args.frame] if args.frame else None
    CONFIG["provider_scan"] = args.provider_scan
    CONFIG["system"] = args.system

    if args.print_env:
        base = "http://%s:%d" % (args.host, args.port)
        print("export ANTHROPIC_BASE_URL=%s" % base)
        print("export OPENAI_BASE_URL=%s/v1" % base)
        print("export GODFATHER_PROXY=1")
        return 0

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    sys.stderr.write("godfather proxy on http://%s:%d\n" % (args.host, args.port))
    sys.stderr.write("  agent: %s\n" % (args.agent or "auto"))
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
