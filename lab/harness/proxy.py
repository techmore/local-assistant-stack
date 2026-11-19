# SPDX-License-Identifier: MIT
"""Logging pass-through proxy: Hermes -> this (127.0.0.1) -> llama-server.

Why: (1) records exactly what Hermes sends (system prompt size, tool list
size, prompt tokens) and what comes back (tool calls, timings); (2) lets a
lever change request parameters (thinking on/off, sampling) without relying
on Hermes config. Overrides are read from run/proxy_overrides.json on every
request. Standard library only. Binds 127.0.0.1.
"""
import json
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent / "run"
UPSTREAM = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:18431"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18432
DUMP_FIRST = RUN / "proxy_last_request.json"


def overrides():
    try:
        return json.loads((RUN / "proxy_overrides.json").read_text())
    except Exception:
        return {}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _forward(self, body=None):
        req = urllib.request.Request(UPSTREAM + self.path, data=body, method=self.command)
        for k in ("Authorization", "Content-Type", "Accept"):
            if self.headers.get(k):
                req.add_header(k, self.headers[k])
        return urllib.request.urlopen(req, timeout=900)

    def do_GET(self):
        try:
            with self._forward() as r:
                data = r.read()
                self.send_response(r.status)
                self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        rec = {"t": time.time(), "path": self.path}
        try:
            body = json.loads(raw)
        except Exception:
            body = None
        if isinstance(body, dict) and "messages" in body:
            body.update(overrides())
            if body.get("stream"):
                body.setdefault("stream_options", {})["include_usage"] = True
            msgs = body["messages"]
            sys_txt = "\n".join(m["content"] if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
                                for m in msgs if m.get("role") in ("system", "developer"))
            rec.update(n_messages=len(msgs), system_chars=len(sys_txt), n_tools=len(body.get("tools") or []),
                       tools_chars=len(json.dumps(body.get("tools") or [])),
                       tool_names=[t.get("function", {}).get("name") for t in body.get("tools") or []],
                       stream=bool(body.get("stream")),
                       params={k: body[k] for k in body if k not in ("messages", "tools")})
            DUMP_FIRST.write_text(json.dumps(body, indent=1))
            raw = json.dumps(body).encode()
        t0 = time.time()
        try:
            r = self._forward(raw)
        except urllib.error.HTTPError as e:
            data = e.read()
            rec.update(status=e.code, error=data[:500].decode("utf8", "replace"))
            self._log(rec)
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        with r:
            self.send_response(r.status)
            ctype = r.headers.get("Content-Type", "application/json")
            self.send_header("Content-Type", ctype)
            content, calls, usage, timings, ttft = "", {}, None, None, None
            if "event-stream" in ctype:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for line in r:
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
                    self.wfile.flush()
                    s = line.decode("utf8", "replace").strip()
                    if not s.startswith("data:") or s == "data: [DONE]":
                        continue
                    try:
                        ch = json.loads(s[5:])
                    except Exception:
                        continue
                    usage = ch.get("usage") or usage
                    timings = ch.get("timings") or timings
                    for c in ch.get("choices") or []:
                        d = c.get("delta") or {}
                        if ttft is None and (d.get("content") or d.get("reasoning_content") or d.get("tool_calls")):
                            ttft = time.time() - t0
                        content += d.get("content") or ""
                        for tc in d.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", 0), {"name": "", "arguments": ""})
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            else:
                data = r.read()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                try:
                    d = json.loads(data)
                    usage, timings = d.get("usage"), d.get("timings")
                    m = d["choices"][0]["message"]
                    content = m.get("content") or ""
                    calls = {i: {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}
                             for i, tc in enumerate(m.get("tool_calls") or [])}
                except Exception:
                    pass
            rec.update(status=r.status, wall_s=round(time.time() - t0, 3), ttft_s=ttft and round(ttft, 3), usage=usage,
                       timings=timings, content=content[:4000], tool_calls=[calls[k] for k in sorted(calls)])
            self._log(rec)

    def _log(self, rec):
        with open(RUN / "proxy.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
