#!/usr/bin/env python3
"""
Lightweight reverse proxy that fixes Cursor's array-format content
before forwarding to Sub2Api.

Cursor sends: {"content": [{"type": "text", "text": "hello"}]}
Sub2Api needs: {"content": "hello"}

Listens on :8081, forwards to localhost:8080
"""

import http.server
import json
import urllib.request
import urllib.error
import threading
import sys
import io


UPSTREAM = "http://127.0.0.1:8080"


def fix_messages(body):
    """Stub - array content is now handled by Sub2Api directly."""
    return body


def inject_reasoning(body):
    """Inject max reasoning/thinking params if not present."""
    # OpenAI reasoning_effort (for o-series, gpt-5.x etc.)
    if "reasoning_effort" not in body:
        body["reasoning_effort"] = "xhigh"
    return body


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        # Only transform /v1/chat/completions requests
        if self.path in ("/v1/chat/completions", "/v1/chat/completions/"):
            try:
                body = json.loads(raw_body)
                # Log key request params only
                key_params = {
                    "model": body.get("model"),
                    "stream": body.get("stream"),
                    "temperature": body.get("temperature"),
                    "max_tokens": body.get("max_tokens"),
                    "reasoning_effort": body.get("reasoning_effort"),
                    "reasoning": body.get("reasoning"),
                    "thinking": body.get("thinking"),
                    "message_count": len(body.get("messages", [])),
                    "tools_count": len(body.get("tools", [])),
                }
                body = fix_messages(body)
                body = inject_reasoning(body)
                key_params["reasoning_effort"] = body.get("reasoning_effort")
                key_params = {k: v for k, v in key_params.items() if v is not None}
                sys.stderr.write(f"[proxy] params: {json.dumps(key_params)}\n")
                raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            except (json.JSONDecodeError, Exception):
                pass  # Forward as-is if not valid JSON

        self._proxy(raw_body)

    def do_GET(self):
        self._proxy(None)

    def do_PUT(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length else None
        self._proxy(raw_body)

    def do_DELETE(self):
        self._proxy(None)

    def do_OPTIONS(self):
        self._proxy(None)

    def do_PATCH(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length else None
        self._proxy(raw_body)

    def _proxy(self, body):
        url = UPSTREAM + self.path

        # Build headers, skip hop-by-hop
        skip = {"host", "transfer-encoding", "connection"}
        headers = {}
        for key, val in self.headers.items():
            if key.lower() not in skip:
                headers[key] = val
        if body is not None:
            headers["Content-Length"] = str(len(body))

        req = urllib.request.Request(
            url, data=body, headers=headers, method=self.command
        )

        try:
            resp = urllib.request.urlopen(req, timeout=300)
            status = resp.status
            resp_headers = resp.getheaders()

            self.send_response(status)
            is_stream = False
            for k, v in resp_headers:
                kl = k.lower()
                if kl in ("transfer-encoding", "connection"):
                    continue
                self.send_header(k, v)
                if kl == "content-type" and "text/event-stream" in v:
                    is_stream = True
            self.end_headers()

            if is_stream:
                # Stream SSE responses, converting reasoning_content to content
                in_reasoning = False
                reasoning_ended = False
                buf = ""
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buf += chunk.decode('utf-8', errors='replace')
                    # Process complete SSE lines
                    while '\n' in buf:
                        line, buf = buf.split('\n', 1)
                        line = line.strip()
                        if not line:
                            # Empty line = SSE event boundary
                            self.wfile.write(b'\n')
                            self.wfile.flush()
                            continue
                        if line == 'data: [DONE]':
                            self.wfile.write(b'data: [DONE]\n\n')
                            self.wfile.flush()
                            continue
                        if line.startswith('data: '):
                            try:
                                d = json.loads(line[6:])
                                delta = d.get('choices', [{}])[0].get('delta', {})
                                if 'reasoning_content' in delta:
                                    rc = delta.pop('reasoning_content')
                                    # Inject thinking marker at start
                                    if not in_reasoning:
                                        in_reasoning = True
                                        rc = "🧠 **Thinking...**\n\n" + rc
                                    delta['content'] = rc
                                elif 'content' in delta and in_reasoning and not reasoning_ended:
                                    # First content chunk after reasoning
                                    reasoning_ended = True
                                    delta['content'] = "\n\n---\n\n" + delta['content']
                                out = 'data: ' + json.dumps(d, ensure_ascii=False) + '\n'
                                self.wfile.write(out.encode('utf-8'))
                                self.wfile.flush()
                            except (json.JSONDecodeError, Exception):
                                self.wfile.write((line + '\n').encode('utf-8'))
                                self.wfile.flush()
                        else:
                            self.wfile.write((line + '\n').encode('utf-8'))
                            self.wfile.flush()
                # Flush remaining buffer
                if buf.strip():
                    self.wfile.write(buf.encode('utf-8'))
                    self.wfile.flush()
            else:
                self.wfile.write(resp.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                kl = k.lower()
                if kl in ("transfer-encoding", "connection"):
                    continue
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(e.read())

        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            err = json.dumps({"error": {"message": str(e), "type": "proxy_error"}})
            self.wfile.write(err.encode())

    def log_message(self, format, *args):
        sys.stderr.write(f"[proxy] {args[0]} {args[1]} {args[2]}\n")


def run(port=8081):
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), ProxyHandler)
    print(f"[cursor-proxy] Listening on 0.0.0.0:{port} -> {UPSTREAM}")
    server.serve_forever()


if __name__ == "__main__":
    run()
