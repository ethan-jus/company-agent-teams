import json
import sqlite3
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

DEEPSEEK_API = "https://api.deepseek.com"
PORT = 8800
DB_PATH = "quota.db"
CONFIG_PATH = "../config/quota-defaults.json"

# 自定义模型名 -> 真实 DeepSeek 模型名
MODEL_MAP = {
    "ds-pro-agent": "deepseek-v4-pro",
    "ds-flash-agent": "deepseek-v4-flash",
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            timestamp REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_monthly (
            agent_id TEXT PRIMARY KEY,
            month TEXT NOT NULL,
            total_tokens INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"monthly_tokens": 5000000, "rate_per_minute": 10, "daily_warn_tokens": 400000, "enabled": True}


def get_agent_id(body):
    """从请求体中提取 agent_id，使用 model 字段作为标识"""
    model = body.get("model", "")
    if model in MODEL_MAP:
        return model
    return None


def check_quota(agent_id, config):
    """检查额度，返回 (allowed, reason)"""
    monthly_limit = config["monthly_tokens"]
    rate_limit = config["rate_per_minute"]
    now = time.time()
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 月度检查
    cur.execute("SELECT total_tokens FROM agent_monthly WHERE agent_id=? AND month=?", (agent_id, month_key))
    row = cur.fetchone()
    month_used = row[0] if row else 0
    if month_used >= monthly_limit:
        conn.close()
        return False, f"monthly token limit exceeded ({month_used}/{monthly_limit})"

    # 频率检查（最近1分钟请求数）
    cutoff = now - 60
    cur.execute("SELECT COUNT(*) FROM usage_log WHERE agent_id=? AND timestamp>?", (agent_id, cutoff))
    recent_count = cur.fetchone()[0]
    if recent_count >= rate_limit:
        conn.close()
        return False, f"rate limit exceeded ({recent_count}/min, max {rate_limit})"

    conn.close()
    return True, ""


def record_usage(agent_id, real_model, usage_data, config):
    """记录用量到 SQLite"""
    prompt_tokens = usage_data.get("prompt_tokens", 0)
    completion_tokens = usage_data.get("completion_tokens", 0)
    total_tokens = usage_data.get("total_tokens", 0)
    now = time.time()
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO usage_log (agent_id, model, prompt_tokens, completion_tokens, total_tokens, timestamp) VALUES (?,?,?,?,?,?)",
        (agent_id, real_model, prompt_tokens, completion_tokens, total_tokens, now),
    )
    conn.execute("""
        INSERT INTO agent_monthly (agent_id, month, total_tokens)
        VALUES (?, ?, ?)
        ON CONFLICT(agent_id, month) DO UPDATE SET total_tokens = total_tokens + ?
    """, (agent_id, month_key, total_tokens, total_tokens))

    # 日告警检查
    daily_warn = config.get("daily_warn_tokens", 400000)
    today = datetime.now().date()
    day_start = time.mktime(today.timetuple())
    cur = conn.cursor()
    cur.execute("SELECT SUM(total_tokens) FROM usage_log WHERE agent_id=? AND timestamp>=?", (agent_id, day_start))
    daily_total = cur.fetchone()[0] or 0
    if daily_total > daily_warn:
        print(f"[WARN] {agent_id} daily usage {daily_total} exceeds warning threshold {daily_warn}")

    conn.commit()
    conn.close()


class ProxyHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len))
        agent_id = get_agent_id(body)
        config = load_config()

        if agent_id:
            allowed, reason = check_quota(agent_id, config)
            if not allowed:
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "quota_exceeded",
                    "message": reason,
                    "agent_id": agent_id,
                }).encode())
                return

        # 映射模型名
        model = body.get("model", "")
        real_model = MODEL_MAP.get(model, model)
        body["model"] = real_model

        # 转发到 DeepSeek
        req = urllib.request.Request(
            f"{DEEPSEEK_API}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": self.headers.get("Authorization", ""),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = json.loads(resp.read())
                if agent_id and "usage" in resp_body:
                    record_usage(agent_id, real_model, resp_body["usage"], config)
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp_body).encode())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    init_db()
    server = HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"Proxy listening on http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("Proxy stopped")
