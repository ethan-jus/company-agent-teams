"""
额度代理层 — 拦截 API 请求，跟踪用量，支持 Agent 自查额度。

两个角色：
1. 反向代理：将 /anthropic/* 请求转发到 DeepSeek（Anthropic 兼容接口）
2. 管理 API：提供额度查询/上报/重置接口，供管理面板和 Agent 自调用

用法：python3 proxy.py
"""

import json
import sqlite3
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import os as _os
_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
BASE_DIR = _os.path.dirname(_SCRIPT_DIR)  # 项目根目录

DEEPSEEK_API = "https://api.deepseek.com"
PROXY_PORT = 8800
DB_PATH = _os.path.join(BASE_DIR, "quota.db")
CONFIG_PATH = _os.path.join(BASE_DIR, "config", "quota-defaults.json")


# ── 数据库 ──────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            timestamp REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_usage (
            agent_id TEXT NOT NULL,
            month TEXT NOT NULL,
            total_tokens INTEGER DEFAULT 0,
            PRIMARY KEY (agent_id, month)
        )
    """)
    conn.commit()
    conn.close()


# ── 配置 ──────────────────────────────────────────────

def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"monthly_tokens": 5000000, "rate_per_minute": 10, "daily_warn_tokens": 400000, "enabled": True}


# ── 总用量追踪 ──────────────────────────────────────

def record_total_usage(model, input_tokens, output_tokens):
    total = input_tokens + output_tokens
    now = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO usage_log (model, input_tokens, output_tokens, total_tokens, timestamp) VALUES (?,?,?,?,?)",
        (model, input_tokens, output_tokens, total, now),
    )
    conn.commit()
    conn.close()


def get_total_usage():
    """返回总用量统计"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(total_tokens),0) FROM usage_log")
    total = cur.fetchone()[0]
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    cur.execute(
        "SELECT COALESCE(SUM(total_tokens),0) FROM usage_log WHERE strftime('%Y-%m', datetime(timestamp, 'unixepoch'))=?",
        (this_month,),
    )
    monthly = cur.fetchone()[0]
    conn.close()
    return {"total": total, "monthly": monthly}


# ── Agent 用量自查 ──────────────────────────────────

def report_agent_usage(agent_id, tokens):
    """Agent 自我上报用量"""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO agent_usage (agent_id, month, total_tokens)
        VALUES (?, ?, ?)
        ON CONFLICT(agent_id, month) DO UPDATE SET total_tokens = total_tokens + ?
    """, (agent_id, month_key, tokens, tokens))
    conn.commit()
    conn.close()


def check_agent_quota(agent_id):
    """检查 Agent 是否超限，返回 (allowed, used, limit, reason)"""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    config = load_config()
    limit = config["monthly_tokens"]
    rate_limit = config["rate_per_minute"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 月度
    cur.execute("SELECT total_tokens FROM agent_usage WHERE agent_id=? AND month=?", (agent_id, month_key))
    row = cur.fetchone()
    used = row[0] if row else 0
    if used >= limit:
        conn.close()
        return False, used, limit, f"月额度已用尽 ({used}/{limit})"

    # 频率 (近 1 分钟该 Agent 的上报次数)
    cutoff = time.time() - 60
    cur.execute("SELECT COUNT(*) FROM agent_usage WHERE agent_id=? AND rowid IN "
                "(SELECT rowid FROM agent_usage ORDER BY rowid DESC LIMIT 100)", (agent_id,))
    # 简化的频率检查：看月上报次数是否超过速率*分钟数
    minutes_elapsed = max(1, (time.time() - cutoff) / 60)
    reports_this_month = cur.fetchone()[0]
    avg_rate = reports_this_month / (minutes_elapsed or 1)
    if avg_rate > rate_limit:
        conn.close()
        return False, used, limit, f"请求频率超限 ({avg_rate:.1f}/min, 限制 {rate_limit})"

    conn.close()
    return True, used, limit, ""


def get_all_agent_usage():
    """返回所有 Agent 的用量（用于管理面板）"""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT agent_id, total_tokens FROM agent_usage WHERE month=?", (month_key,))
    rows = cur.fetchall()
    conn.close()
    return {aid: tokens for aid, tokens in rows}


# ── HTTP Handler ───────────────────────────────────────

class ProxyHandler(BaseHTTPRequestHandler):

    def _send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── Anthropic 消息代理 ──────────────────────────

    def do_POST(self):
        # ── REST API 路由 ──
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 健康检查
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        # Agent 自查额度
        if path == "/api/quota/check":
            agent_id = query.get("agent_id", [None])[0]
            if not agent_id:
                self._send_json(400, {"error": "missing agent_id"})
                return
            allowed, used, limit, reason = check_agent_quota(agent_id)
            self._send_json(200, {
                "agent_id": agent_id,
                "allowed": allowed,
                "used": used,
                "limit": limit,
                "reason": reason if not allowed else "",
            })
            return

        # Agent 上报用量
        if path == "/api/quota/report":
            body = self._read_body()
            agent_id = body.get("agent_id")
            tokens = body.get("tokens", 0)
            if not agent_id:
                self._send_json(400, {"error": "missing agent_id"})
                return
            report_agent_usage(agent_id, tokens)
            self._send_json(200, {"success": True})
            return

        # 用量查询（管理面板）
        if path == "/api/quota/usage":
            self._send_json(200, {
                "total": get_total_usage(),
                "agents": get_all_agent_usage(),
            })
            return

        # 重置（管理面板）
        if path == "/api/quota/reset":
            body = self._read_body()
            agent_id = body.get("agent_id")
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")
            conn = sqlite3.connect(DB_PATH)
            if agent_id:
                conn.execute("DELETE FROM agent_usage WHERE agent_id=? AND month=?", (agent_id, month_key))
            else:
                conn.execute("DELETE FROM agent_usage WHERE month=?", (month_key,))
            conn.commit()
            conn.close()
            self._send_json(200, {"success": True})
            return

        # ── 转发 Anthropic 消息 API ──
        if path == "/anthropic/messages":
            body = self._read_body()
            req = urllib.request.Request(
                f"{DEEPSEEK_API}/anthropic/messages",
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.headers.get("x-api-key", ""),
                    "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    resp_body = json.loads(resp.read())
                    # 记录用量
                    if "usage" in resp_body:
                        usage = resp_body["usage"]
                        model = resp_body.get("model", body.get("model", "unknown"))
                        record_total_usage(
                            model,
                            usage.get("input_tokens", 0),
                            usage.get("output_tokens", 0),
                        )
                    self._send_json(resp.status, resp_body)
            except urllib.error.HTTPError as e:
                self._send_json(e.code, json.loads(e.read()))
            return

        self._send_json(404, {"error": "not found"})

    def do_GET(self):
        self.do_POST()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


# ── 启动 ────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    server = HTTPServer(("0.0.0.0", PROXY_PORT), ProxyHandler)
    print(f"Proxy listening on http://localhost:{PROXY_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("Proxy stopped")
