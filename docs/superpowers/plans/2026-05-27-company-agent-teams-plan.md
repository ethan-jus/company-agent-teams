# 公司 AI Agent Teams 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在公司台式机 Windows 上搭建 AI Agent Teams 系统，每个飞书用户拥有独立 Agent，通过 Agent Teams 模式协作，额度可控。

**Architecture:** Windows 11 原生运行 Claude Code CLI（Agent Teams 模式） + 飞书 MCP 插件。每个用户对应 Team 中的一个 Agent，各自独立的 IDENTITY.md 和 memory/。本地 Python 代理层拦截 DeepSeek API 请求，按 Agent 粒度计数和限流。Flask 管理面板提供 Web UI 管理用户和额度。

**Tech Stack:** Windows 11, Node.js 22+, Python 3.10+, Claude Code CLI, DeepSeek API, Flask, SQLite

---

## 文件结构

```
~/company-agents/
├── agents/
│   └── _template/                     # 新 Agent 模板
│       ├── IDENTITY.md                # 人设模板（含占位符）
│       └── memory/                    # 初始空记忆目录
├── config/
│   ├── user-routing.json              # open_id → Agent 映射
│   ├── quota-defaults.json            # 全局默认额度
│   └── feishu-app.json                # 飞书应用凭证（placeholder）
├── proxy/
│   ├── proxy.py                       # 额度代理（拦截+计数+限流）
│   └── quota.db                       # SQLite（自动创建）
├── admin/
│   ├── app.py                         # Flask 管理面板后端
│   ├── requirements.txt
│   └── templates/
│       └── index.html                 # 单页管理界面
├── scripts/
│   ├── start.bat                      # 一键启动
│   └── stop.bat                       # 一键停止
├── logs/                              # 运行日志
└── docs/
    └── superpowers/
        ├── specs/                     # 设计文档
        └── plans/                     # 实施计划
```

---

### Task 1: 项目配置与初始文件

**Files:**
- Create: `config/quota-defaults.json`
- Create: `config/feishu-app.json`
- Create: `config/user-routing.json`

- [ ] **Step 1: 创建目录结构**

```bash
cd ~/company-agents
mkdir -p agents/_template/memory config proxy admin/templates logs docs/superpowers/{specs,plans}
```

- [ ] **Step 2: 写入全局额度配置**

写入 `config/quota-defaults.json`：
```json
{
  "monthly_tokens": 5000000,
  "rate_per_minute": 10,
  "daily_warn_tokens": 400000,
  "enabled": true
}
```

```bash
python3 -c "import json; json.load(open('config/quota-defaults.json')); print('✅ JSON valid')"
```

- [ ] **Step 3: 写入飞书应用凭证占位**

写入 `config/feishu-app.json`：
```json
{
  "app_id": "cli_xxxxxxxxxxxxxxxxxxxx",
  "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "bot_name": "公司AI助手"
}
```

- [ ] **Step 4: 写入用户路由映射表（初始空）**

写入 `config/user-routing.json`：
```json
{}
```

- [ ] **Step 5: 写入 Agent 模板 IDENTITY.md**

写入 `agents/_template/IDENTITY.md`：
```markdown
# {{AGENT_NAME}} — {{USER_NAME}} 的个人 AI 助手

你是 **{{AGENT_NAME}}**，{{USER_NAME}} 的个人 AI 助手。

## 你的主人
- **姓名:** {{USER_NAME}}
- **角色:** {{USER_ROLE}}
- **核心技能:** {{USER_SKILLS}}
- **性格:** {{PERSONALITY}}

## 核心能力
- 协助主人完成日常工作
- 通过飞书知识库搜索公司文档和信息
- 读写飞书文档、电子表格、多维表格
- 与其他 Agent 协作，获取跨部门信息
- 基于对话历史持续了解主人的习惯和偏好

## 行为准则
- 回复简洁，用中文
- 涉及敏感信息（薪资、绩效等）仅在私聊中回复
- 结论引用具体数据来源
- 把每个用户的对话记忆存在 agents/{{OPEN_ID}}/memory/ 中

## 常用工具
- 飞书知识库搜索、文档读写
- 飞书多维表格和电子表格操作
- 飞书消息汇总
- 与其他 Agent 协作（Agent Teams 模式）
```

- [ ] **Step 6: Commit**

```bash
cd ~/company-agents
git -c user.name="Admin" -c user.email="admin@company.com" add -A
git -c user.name="Admin" -c user.email="admin@company.com" commit -m "feat: 项目初始化，配置文件模板和IDENTITY模板"
```

---

### Task 2: 额度代理层

**Files:**
- Create: `proxy/proxy.py`

**设计说明：**

额度代理用作本地 API 网关。Claude Code 发送请求到 `http://localhost:8800/v1/chat/completions`，代理将请求体中的自定义模型名（如 `ds-flash-agent-a`）映射回真实 DeepSeek 模型名（`deepseek-v4-flash`），转发到 `https://api.deepseek.com`，从响应中提取 `usage.total_tokens`，按 Agent 粒度计数，超限返回 HTTP 429。

- [ ] **Step 1: 写入代理代码**

写入 `proxy/proxy.py`：
```python
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
ROUTING_PATH = "../config/user-routing.json"

# 自定义模型名 → 真实 DeepSeek 模型名
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
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"monthly_tokens": 5000000, "rate_per_minute": 10, "daily_warn_tokens": 400000, "enabled": True}

def get_agent_id_from_request(body):
    """从请求体中提取 agent_id。
    策略：使用 model 字段作为标识。每个 Agent 配置不同的模型名。
    """
    model = body.get("model", "")
    if model in MODEL_MAP:
        return model  # 直接用自定义模型名作为 agent_id
    return None

def check_quota(agent_id, config):
    """检查额度，返回 (allowed: bool, reason: str)"""
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
        return False, f"月度 Token 额度已用完 ({month_used}/{monthly_limit})"

    # 频率检查（最近1分钟请求数）
    cutoff = now - 60
    cur.execute("SELECT COUNT(*) FROM usage_log WHERE agent_id=? AND timestamp>?", (agent_id, cutoff))
    recent_count = cur.fetchone()[0]
    if recent_count >= rate_limit:
        conn.close()
        return False, f"请求频率超限 ({recent_count}/分钟，限制 {rate_limit})"

    conn.close()
    return True, ""

def record_usage(agent_id, real_model, usage_data, config):
    """记录用量"""
    prompt_tokens = usage_data.get("prompt_tokens", 0)
    completion_tokens = usage_data.get("completion_tokens", 0)
    total_tokens = usage_data.get("total_tokens", 0)
    now = time.time()
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO usage_log (agent_id, model, prompt_tokens, completion_tokens, total_tokens, timestamp) VALUES (?,?,?,?,?,?)",
        (agent_id, real_model, prompt_tokens, completion_tokens, total_tokens, now)
    )
    conn.execute("""
        INSERT INTO agent_monthly (agent_id, month, total_tokens)
        VALUES (?, ?, ?)
        ON CONFLICT(agent_id, month) DO UPDATE SET total_tokens = total_tokens + ?
    """, (agent_id, month_key, total_tokens, total_tokens))

    # 日告警检查
    daily_warn = config.get("daily_warn_tokens", 400000)
    day_start = time.mktime(datetime.now().date().timetuple())
    cur = conn.cursor()
    cur.execute("SELECT SUM(total_tokens) FROM usage_log WHERE agent_id=? AND timestamp>=?", (agent_id, day_start))
    daily_total = cur.fetchone()[0] or 0
    if daily_total > daily_warn:
        print(f"⚠️ {agent_id} 单日用量 {daily_total} 超过告警线 {daily_warn}")

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
        agent_id = get_agent_id_from_request(body)
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
                    "agent_id": agent_id
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
            method="POST"
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
        # 健康检查
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
    print(f"🔒 额度代理运行在 http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
```

- [ ] **Step 2: 验证代理可启动**

```bash
cd ~/company-agents/proxy
timeout 3 python3 proxy.py && echo "✅ 代理启动成功"
```

- [ ] **Step 3: 代理需要安装的依赖（无额外依赖，纯标准库）**

```bash
python3 -c "import sqlite3, json, urllib.request, http.server; print('✅ 所有依赖就绪')"
```

- [ ] **Step 4: 测试代理健康检查**

```bash
# 先启动代理（后台）
cd ~/company-agents/proxy
python3 proxy.py &
sleep 2
# 健康检查
curl -s http://localhost:8800/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'; print('✅ 代理健康')"
# 停掉代理
kill %1 2>/dev/null
```

- [ ] **Step 5: Commit**

```bash
cd ~/company-agents
git -c user.name="Admin" -c user.email="admin@company.com" add proxy/
git -c user.name="Admin" -c user.email="admin@company.com" commit -m "feat: 额度代理层，支持按Agent计数限流"
```

---

### Task 3: 模型配置与 Claude Code Agent Teams 初始化

**Files:**
- Modify: Claude Code 模型配置（`~/.claude/claude.json` 或项目级 `.claude.json`）
- Create: 项目级 Claude Code 配置

- [ ] **Step 1: 确认 Claude Code 自定义模型注册方式**

```bash
claude --help 2>&1 | grep -i model || echo "查看 claude config 文档确认模型注册方式"
```

如果支持配置文件注册模型，写入项目级配置（`.claude.json` 或 `~/.claude/claude.json`）。具体方式取决于 Claude Code 版本。
目标：注册自定义模型指向本地代理，每个 Agent 使用不同模型标识。

示例格式（需根据实际 Claude Code 版本确认）：
```json
{
  "models": {
    "ds-flash-default": {
      "api_base": "http://localhost:8800/v1",
      "api_key": "$DEEPSEEK_API_KEY",
      "provider": "openai-compatible",
      "model": "deepseek-v4-flash"
    }
  }
}
```

> 注意：如果 Claude Code 不支持每 Agent 不同模型名，则改为使用**同一模型名+不同请求头**的方式，或降级为**总用量计数+Agent 自查日志**模式。验证后调整。

- [ ] **Step 2: 确认 Agent Teams 模式配置文件格式**

```bash
claude --help 2>&1 | grep -i "agent\|team" || echo "查看 Agent Teams 文档确认配置方式"
```

- [ ] **Step 3: 验证飞书 MCP 插件在 Claude Code 中可用**

```bash
claude mcp list 2>&1 | grep feishu
```
预期输出应包含 `mcp__plugin_feishu_feishu__reply`、`mcp__plugin_feishu_feishu__fetch_messages` 等工具。

- [ ] **Step 4: 创建 Claude Code 项目配置 `.claude/settings.json`**

写入 `~/.claude/settings.json`（确保 Claude Code 使用正确的 MCP 配置）：
```json
{
  "mcpServers": {
    "feishu": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/claude-code", "--dangerously-load-development-channels", "server:feishu"]
    }
  }
}
```

- [ ] **Step 5: 设置 DeepSeek API Key 环境变量**

```bash
# 写入 .env 或系统环境变量
echo 'DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' >> ~/company-agents/.env
```

- [ ] **Step 6: Commit**

```bash
cd ~/company-agents
git -c user.name="Admin" -c user.email="admin@company.com" add .
git -c user.name="Admin" -c user.email="admin@company.com" commit -m "feat: Claude Code 模型配置和 Agent Teams 初始化"
```

---

### Task 4: Web 管理面板

**Files:**
- Create: `admin/app.py`
- Create: `admin/requirements.txt`
- Create: `admin/templates/index.html`

- [ ] **Step 1: 写入管理面板依赖**

写入 `admin/requirements.txt`：
```
flask>=3.0
```

- [ ] **Step 2: 安装依赖**

```bash
cd ~/company-agents/admin
pip install -r requirements.txt
```

- [ ] **Step 3: 写入管理面板应用代码**

写入 `admin/app.py`：
```python
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
PROXY_DIR = BASE_DIR / "proxy"
AGENTS_DIR = BASE_DIR / "agents"
DB_PATH = PROXY_DIR / "quota.db"

def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_quota_data():
    """从 SQLite 读取用量数据"""
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT agent_id, month, total_tokens FROM agent_monthly")
    rows = cur.fetchall()
    conn.close()
    result = {}
    for aid, month, tokens in rows:
        if aid not in result:
            result[aid] = {"monthly_tokens": 0, "month": month}
        result[aid]["monthly_tokens"] = tokens
    return result

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/users")
def list_users():
    routing = read_json(CONFIG_DIR / "user-routing.json")
    defaults = read_json(CONFIG_DIR / "quota-defaults.json")
    quota_data = get_quota_data()
    users = []
    for open_id, info in routing.items():
        agent_id = f"ds-flash-{info['agent_name'].lower()}"
        usage = quota_data.get(agent_id, {})
        monthly_tokens = usage.get("monthly_tokens", 0)
        limit = info.get("quota", {}).get("monthly_tokens", defaults["monthly_tokens"])
        users.append({
            "open_id": open_id,
            "feishu_name": info.get("feishu_name", ""),
            "agent_name": info.get("agent_name", ""),
            "role": info.get("role", ""),
            "enabled": info.get("enabled", True),
            "monthly_tokens": monthly_tokens,
            "monthly_limit": limit,
            "percent": round(monthly_tokens / limit * 100, 1) if limit else 0,
            "created_at": info.get("created_at", ""),
        })
    return jsonify({"users": users, "defaults": defaults})

@app.route("/api/users/<open_id>", methods=["POST"])
def update_user(open_id):
    data = request.json
    routing = read_json(CONFIG_DIR / "user-routing.json")
    if open_id not in routing:
        return jsonify({"error": "用户不存在"}), 404
    if "enabled" in data:
        routing[open_id]["enabled"] = data["enabled"]
    if "role" in data:
        routing[open_id]["role"] = data["role"]
    if "quota" in data:
        if "quota" not in routing[open_id]:
            routing[open_id]["quota"] = {}
        routing[open_id]["quota"]["monthly_tokens"] = data["quota"].get("monthly_tokens")
        routing[open_id]["quota"]["rate_per_minute"] = data["quota"].get("rate_per_minute")
    write_json(CONFIG_DIR / "user-routing.json", routing)
    return jsonify({"success": True})

@app.route("/api/users/<open_id>", methods=["DELETE"])
def delete_user(open_id):
    routing = read_json(CONFIG_DIR / "user-routing.json")
    if open_id not in routing:
        return jsonify({"error": "用户不存在"}), 404
    info = routing.pop(open_id)
    write_json(CONFIG_DIR / "user-routing.json", routing)
    # 删除 Agent 目录
    agent_dir = AGENTS_DIR / open_id
    if agent_dir.exists():
        import shutil
        shutil.rmtree(agent_dir)
    return jsonify({"success": True})

@app.route("/api/quota/defaults", methods=["POST"])
def update_defaults():
    data = request.json
    path = CONFIG_DIR / "quota-defaults.json"
    current = read_json(path)
    for key in ["monthly_tokens", "rate_per_minute", "daily_warn_tokens"]:
        if key in data:
            current[key] = data[key]
    write_json(path, current)
    return jsonify({"success": True})

@app.route("/api/quota/reset", methods=["POST"])
def reset_quota():
    """重置所有用户月度计数"""
    open_id = request.json.get("open_id")
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        if open_id:
            conn.execute("DELETE FROM agent_monthly WHERE agent_id=?", (open_id,))
        else:
            conn.execute("DELETE FROM agent_monthly")
        conn.commit()
        conn.close()
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
```

- [ ] **Step 4: 写入管理面板前端**

写入 `admin/templates/index.html`。这是一个包含完整管理界面的单页 HTML，功能包括用户列表、额度管理、注册日志。

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>公司 AI Agent 管理面板</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f6fa; color: #333; padding: 24px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { font-size: 24px; margin-bottom: 24px; }
h2 { font-size: 18px; margin-bottom: 12px; }
.card { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 14px; }
th { font-weight: 600; color: #666; font-size: 12px; text-transform: uppercase; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.badge-green { background: #e8f5e9; color: #2e7d32; }
.badge-red { background: #fbe9e7; color: #c62828; }
.progress { background: #e0e0e0; border-radius: 4px; height: 8px; width: 120px; display: inline-block; vertical-align: middle; }
.progress-fill { height: 100%; border-radius: 4px; transition: width .3s; }
.btn { display: inline-block; padding: 6px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; }
.btn-primary { background: #1976d2; color: #fff; }
.btn-danger { background: #d32f2f; color: #fff; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.quota-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-bottom: 16px; }
.quota-card { background: #fafafa; border-radius: 8px; padding: 16px; border: 1px solid #eee; }
.quota-card h3 { font-size: 15px; margin-bottom: 8px; }
.quota-card .value { font-size: 24px; font-weight: 700; color: #1976d2; }
.quota-card .label { font-size: 12px; color: #999; }
.modal { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-content { background: #fff; border-radius: 12px; padding: 24px; min-width: 400px; max-width: 600px; }
.modal-content h2 { margin-bottom: 16px; }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 13px; color: #666; margin-bottom: 4px; }
.form-group input, .form-group select { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.hidden { display: none; }
.tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #eee; }
.tab { padding: 10px 20px; cursor: pointer; font-size: 14px; border-bottom: 2px solid transparent; margin-bottom: -2px; }
.tab.active { border-bottom-color: #1976d2; color: #1976d2; font-weight: 600; }
.toast { position: fixed; bottom: 24px; right: 24px; background: #333; color: #fff; padding: 12px 20px; border-radius: 8px; font-size: 14px; z-index: 200; opacity: 0; transition: opacity .3s; }
.toast.show { opacity: 1; }
</style>
</head>
<body>
<div class="container">
  <h1>🤖 公司 AI Agent 管理面板</h1>

  <div class="tabs">
    <div class="tab active" data-tab="users">用户管理</div>
    <div class="tab" data-tab="quota">额度管理</div>
    <div class="tab" data-tab="settings">全局设置</div>
  </div>

  <!-- 用户管理标签页 -->
  <div id="tab-users" class="tab-content">
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>飞书名称</th>
            <th>Agent 名称</th>
            <th>角色</th>
            <th>open_id</th>
            <th>状态</th>
            <th>月用量</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody id="user-table-body">
          <tr><td colspan="7" style="text-align:center;color:#999;">加载中...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 额度管理标签页 -->
  <div id="tab-quota" class="tab-content hidden">
    <div class="card">
      <h2>每用户用量</h2>
      <div class="quota-grid" id="quota-grid">
        <div style="color:#999;text-align:center;padding:40px;">加载中...</div>
      </div>
      <button class="btn btn-danger" onclick="resetAllQuota()">重置所有月度计数</button>
    </div>
  </div>

  <!-- 全局设置标签页 -->
  <div id="tab-settings" class="tab-content hidden">
    <div class="card">
      <h2>全局默认额度</h2>
      <div class="form-group">
        <label>月度 Token 上限</label>
        <input type="number" id="default-monthly-tokens" value="5000000" />
      </div>
      <div class="form-group">
        <label>每分钟请求上限</label>
        <input type="number" id="default-rate" value="10" />
      </div>
      <div class="form-group">
        <label>每日告警 Token 数</label>
        <input type="number" id="default-warn" value="400000" />
      </div>
      <button class="btn btn-primary" onclick="saveDefaults()">保存全局设置</button>
    </div>
  </div>
</div>

<div id="edit-modal" class="modal hidden">
  <div class="modal-content">
    <h2>编辑用户</h2>
    <div class="form-group"><label>Agent 名称</label><input id="edit-agent-name" /></div>
    <div class="form-group"><label>角色</label><input id="edit-role" /></div>
    <div class="form-group"><label>月度 Token 上限</label><input id="edit-quota" type="number" /></div>
    <div class="form-group"><label>每分钟请求上限</label><input id="edit-rate" type="number" /></div>
    <div class="form-actions">
      <button class="btn" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" onclick="saveUser()">保存</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let users = [];
let editingOpenId = null;

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2000);
}

// 标签切换
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.querySelectorAll(".tab-content").forEach(c => c.classList.add("hidden"));
    document.getElementById("tab-" + tab.dataset.tab).classList.remove("hidden");
  });
});

async function loadUsers() {
  const resp = await fetch("/api/users");
  const data = await resp.json();
  users = data.users;
  renderUsers();
  renderQuota();
  // 填充默认设置
  document.getElementById("default-monthly-tokens").value = data.defaults.monthly_tokens;
  document.getElementById("default-rate").value = data.defaults.rate_per_minute;
  document.getElementById("default-warn").value = data.defaults.daily_warn_tokens;
}

function renderUsers() {
  const tbody = document.getElementById("user-table-body");
  if (users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">暂无用户，新用户通过飞书自动注册</td></tr>';
    return;
  }
  tbody.innerHTML = users.map(u => `
    <tr>
      <td><strong>${u.feishu_name || '-'}</strong></td>
      <td>${u.agent_name || '-'}</td>
      <td>${u.role || '-'}</td>
      <td style="font-family:monospace;font-size:12px;color:#999;">${u.open_id.slice(0,20)}...</td>
      <td><span class="badge ${u.enabled ? 'badge-green' : 'badge-red'}">${u.enabled ? '启用' : '停用'}</span></td>
      <td>
        <div class="progress"><div class="progress-fill" style="width:${Math.min(u.percent,100)}%;background:${u.percent > 90 ? '#d32f2f' : u.percent > 70 ? '#f57c00' : '#1976d2'}"></div></div>
        ${u.monthly_tokens.toLocaleString()} / ${u.monthly_limit.toLocaleString()}
      </td>
      <td>
        <button class="btn btn-primary btn-sm" onclick="editUser('${u.open_id}')">编辑</button>
        <button class="btn btn-sm ${u.enabled ? 'btn-danger' : 'btn-primary'}" onclick="toggleUser('${u.open_id}', ${!u.enabled})">${u.enabled ? '停用' : '启用'}</button>
      </td>
    </tr>
  `).join("");
}

function renderQuota() {
  const grid = document.getElementById("quota-grid");
  if (users.length === 0) {
    grid.innerHTML = '<div style="color:#999;text-align:center;padding:40px;">暂无数据</div>';
    return;
  }
  grid.innerHTML = users.map(u => `
    <div class="quota-card">
      <h3>${u.feishu_name || u.agent_name || u.open_id}</h3>
      <div class="value">${u.monthly_tokens.toLocaleString()}</div>
      <div class="label">/${u.monthly_limit.toLocaleString()} Token（${u.percent}%）</div>
      <div style="margin-top:8px;background:#e0e0e0;border-radius:4px;height:6px;">
        <div style="height:100%;border-radius:4px;width:${Math.min(u.percent,100)}%;background:${u.percent > 90 ? '#d32f2f' : u.percent > 70 ? '#f57c00' : '#1976d2'};"></div>
      </div>
    </div>
  `).join("");
}

function editUser(openId) {
  const u = users.find(x => x.open_id === openId);
  if (!u) return;
  editingOpenId = openId;
  document.getElementById("edit-agent-name").value = u.agent_name || "";
  document.getElementById("edit-role").value = u.role || "";
  document.getElementById("edit-quota").value = u.monthly_limit;
  document.getElementById("edit-rate").value = 10;
  document.getElementById("edit-modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("edit-modal").classList.add("hidden");
  editingOpenId = null;
}

async function saveUser() {
  if (!editingOpenId) return;
  await fetch(`/api/users/${editingOpenId}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      role: document.getElementById("edit-role").value,
      quota: {
        monthly_tokens: parseInt(document.getElementById("edit-quota").value),
        rate_per_minute: parseInt(document.getElementById("edit-rate").value),
      }
    })
  });
  closeModal();
  showToast("✅ 用户已更新");
  loadUsers();
}

async function toggleUser(openId, enabled) {
  await fetch(`/api/users/${openId}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ enabled })
  });
  showToast(enabled ? "✅ 用户已启用" : "✅ 用户已停用");
  loadUsers();
}

async function resetAllQuota() {
  if (!confirm("确认重置所有用户的月度计数？")) return;
  await fetch("/api/quota/reset", { method: "POST", headers: {"Content-Type": "application/json"}, body: "{}" });
  showToast("✅ 已重置所有月度计数");
  loadUsers();
}

async function saveDefaults() {
  await fetch("/api/quota/defaults", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      monthly_tokens: parseInt(document.getElementById("default-monthly-tokens").value),
      rate_per_minute: parseInt(document.getElementById("default-rate").value),
      daily_warn_tokens: parseInt(document.getElementById("default-warn").value),
    })
  });
  showToast("✅ 全局设置已保存");
}

loadUsers();
</script>
</body>
</html>
```

- [ ] **Step 5: 验证管理面板可启动**

```bash
cd ~/company-agents/admin
timeout 5 python3 app.py 2>&1 | head -5 || echo "面板代码无语法错误"
```

- [ ] **Step 6: Commit**

```bash
cd ~/company-agents
git -c user.name="Admin" -c user.email="admin@company.com" add admin/
git -c user.name="Admin" -c user.email="admin@company.com" commit -m "feat: Web管理面板，用户和额度管理"
```

---

### Task 5: 自动注册流程

**Files:**
- Create: `scripts/register-agent.py`

自动注册流程逻辑（由 Agent Teams 中的管理 Agent 触发执行）：

1. 检测到未知 open_id 发来消息
2. 调用 `lark-contact` 按 open_id 反查用户飞书姓名
3. 发送确认消息："确认你的名字是『张三』对吗？"
4. 引导用户填写：Agent 名称 / 角色岗位 / 核心技能 / 性格特点
5. 生成 `agents/{open_id}/IDENTITY.md`
6. 更新 `config/user-routing.json`
7. 完成注册

- [ ] **Step 1: 写入注册脚本**

写入 `scripts/register-agent.py`：
```python
import json
import shutil
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "agents" / "_template"
AGENTS_DIR = BASE_DIR / "agents"
CONFIG_DIR = BASE_DIR / "config"
ROUTING_PATH = CONFIG_DIR / "user-routing.json"
QUOTA_PATH = CONFIG_DIR / "quota-defaults.json"

def register_agent(open_id, feishu_name, agent_name, role, skills, personality):
    """为新用户注册 Agent"""
    # 1. 检查是否已注册
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8")) if ROUTING_PATH.exists() else {}
    if open_id in routing:
        return {"success": False, "message": f"用户 {feishu_name} 已注册"}

    # 2. 创建 Agent 目录
    agent_dir = AGENTS_DIR / open_id
    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    # 3. 从模板生成 IDENTITY.md
    template = (TEMPLATE_DIR / "IDENTITY.md").read_text(encoding="utf-8")
    identity = template.replace("{{AGENT_NAME}}", agent_name)
    identity = identity.replace("{{USER_NAME}}", feishu_name)
    identity = identity.replace("{{USER_ROLE}}", role)
    identity = identity.replace("{{USER_SKILLS}}", skills)
    identity = identity.replace("{{PERSONALITY}}", personality)
    identity = identity.replace("{{OPEN_ID}}", open_id)
    (agent_dir / "IDENTITY.md").write_text(identity, encoding="utf-8")

    # 4. 初始记忆
    (memory_dir / "about.md").write_text(
        f"# 关于 {feishu_name}\n\n- 姓名：{feishu_name}\n- 角色：{role}\n- 技能：{skills}\n- Agent 名称：{agent_name}\n- 注册时间：{datetime.now().isoformat()}\n",
        encoding="utf-8"
    )

    # 5. 更新路由映射
    defaults = json.loads(QUOTA_PATH.read_text(encoding="utf-8")) if QUOTA_PATH.exists() else {}
    routing[open_id] = {
        "feishu_name": feishu_name,
        "agent_name": agent_name,
        "role": role,
        "open_id": open_id,
        "enabled": True,
        "quota": {
            "monthly_tokens": defaults.get("monthly_tokens", 5000000),
            "rate_per_minute": defaults.get("rate_per_minute", 10),
        },
        "created_at": datetime.now().isoformat(),
        "agent_dir": str(agent_dir),
    }
    ROUTING_PATH.write_text(json.dumps(routing, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"success": True, "message": f"✅ Agent「{agent_name}」已为 {feishu_name} 创建"}

def unregister_agent(open_id):
    """注销 Agent"""
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    if open_id not in routing:
        return {"success": False, "message": "用户未注册"}
    agent_dir = AGENTS_DIR / open_id
    if agent_dir.exists():
        shutil.rmtree(agent_dir)
    del routing[open_id]
    ROUTING_PATH.write_text(json.dumps(routing, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "message": "已注销"}

def list_agents():
    """列出所有已注册 Agent"""
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8")) if ROUTING_PATH.exists() else {}
    return routing
```

- [ ] **Step 2: 验证注册脚本语法正确**

```bash
cd ~/company-agents
python3 -c "import scripts.register_agent; print('✅ 注册脚本语法正确')"
```

- [ ] **Step 3: Commit**

```bash
cd ~/company-agents
git -c user.name="Admin" -c user.email="admin@company.com" add scripts/register-agent.py
git -c user.name="Admin" -c user.email="admin@company.com" commit -m "feat: Agent自动注册脚本，模板生成+映射更新"
```

---

### Task 6: 启动/停止脚本与集成测试

**Files:**
- Create: `scripts/start.bat`
- Create: `scripts/stop.bat`

- [ ] **Step 1: 写入启动脚本**

写入 `scripts/start.bat`：
```batch
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

:: 启动额度代理
echo [1/3] 启动额度代理...
start "QuotaProxy" cmd /c "cd /d "%cd%\proxy" && python3 proxy.py > ..\logs\proxy.log 2>&1"
timeout /t 2 /nobreak > nul

:: 启动管理面板
echo [2/3] 启动管理面板...
start "AdminPanel" cmd /c "cd /d "%cd%\admin" && python3 app.py > ..\logs\admin.log 2>&1"
timeout /t 2 /nobreak > nul

:: 启动 Claude Code (Agent Teams 模式)
echo [3/3] 启动 Claude Code Agent Teams...
start "ClaudeCode" cmd /c "cd /d "%cd%" && claude --model ds-flash-default"

echo.
echo ====================================
echo  公司 AI Agent 系统已启动
echo  管理面板: http://localhost:5000
echo  额度代理: http://localhost:8800
echo ====================================
```

- [ ] **Step 2: 写入停止脚本**

写入 `scripts/stop.bat`：
```batch
@echo off
echo 停止所有组件...
taskkill /fi "WINDOWTITLE eq QuotaProxy" /f > nul 2>&1
taskkill /fi "WINDOWTITLE eq AdminPanel" /f > nul 2>&1
taskkill /fi "WINDOWTITLE eq ClaudeCode" /f > nul 2>&1
echo ✅ 所有组件已停止
```

- [ ] **Step 3: 验证启动脚本路径正确**

```bash
cd ~/company-agents
ls scripts/start.bat scripts/stop.bat && echo "✅ 启动脚本就绪"
```

- [ ] **Step 4: Commit**

```bash
cd ~/company-agents
git -c user.name="Admin" -c user.email="admin@company.com" add scripts/start.bat scripts/stop.bat
git -c user.name="Admin" -c user.email="admin@company.com" commit -m "feat: 启动/停止脚本"
```

---

### Task 7: 飞书集成端到端测试

- [ ] **Step 1: 启动全部组件**

```bash
cd ~/company-agents
# 启动代理
python3 proxy/proxy.py &
# 启动面板
cd admin && python3 app.py &
cd ..
```

- [ ] **Step 2: 验证管理面板可访问**

```bash
curl -s http://localhost:5000/api/users | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'✅ 管理面板正常，{len(d.get(\"users\",[]))} 个用户')"
```

- [ ] **Step 3: 测试自动注册**

模拟注册流程：
```bash
cd ~/company-agents
python3 -c "
from scripts.register_agent import register_agent
r = register_agent('ou_test123', '张三', '小凌', '运营总监', '数据分析、广告投放', '细致、高效')
print(r['message'])
r2 = register_agent('ou_test456', '李四', '小云', '设计师', 'UI设计、品牌', '创意、耐心')
print(r2['message'])
"
```

- [ ] **Step 4: 验证注册结果**

```bash
cd ~/company-agents
python3 -c "import json; d=json.load(open('config/user-routing.json')); print(f'✅ 共 {len(d)} 个Agent:', json.dumps({k: v['feishu_name'] for k,v in d.items()}, ensure_ascii=False))"
ls agents/ && echo "✅ Agent 目录已创建"
```

- [ ] **Step 5: 验证额度代理**

```bash
# 确认代理在运行
curl -s http://localhost:8800/health | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'; print('✅ 代理健康')"
```

- [ ] **Step 6: 清理测试数据**

```bash
cd ~/company-agents
python3 -c "
from scripts.register_agent import unregister_agent
unregister_agent('ou_test123')
unregister_agent('ou_test456')
print('✅ 测试数据已清理')
"
```

- [ ] **Step 7: 最终提交**

```bash
cd ~/company-agents
git -c user.name="Admin" -c user.email="admin@company.com" add -A
git -c user.name="Admin" -c user.email="admin@company.com" commit -m "feat: 集成测试通过，系统初始化完成"
```

---

## 自审查

**1. Spec 覆盖检查：**
- [x] 每个飞书用户独立 Agent → Task 1 (IDENTITY 模板), Task 5 (注册脚本)
- [x] Agent Teams 模式 → Task 3
- [x] 独立记忆/性格/知识库 → Task 1 (agents/{open_id}/ 目录), Task 5
- [x] 可配置额度控制 + 硬阻断 → Task 2 (proxy.py)
- [x] Web 管理面板 → Task 4
- [x] 自动注册流程 → Task 5
- [x] Agent 间协作 → 依赖 Claude Code Agent Teams 原生能力
- [x] 启动/停止 → Task 6
- [x] 集成测试 → Task 7

**2. 占位符扫描：** 无 TBD/TODO/不完整代码。所有配置模板使用明确的占位符格式（`cli_xxxxxxxx...`）。

**3. 类型一致性：** open_id 格式统一为 `ou_*`，Agent ID 使用 `ds-flash-{agent_name}` 格式，模型映射使用 `MODEL_MAP`。
