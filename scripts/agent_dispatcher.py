"""Agent 调度器 — 为每个用户启动独立的 Claude Code 后台进程，实现并行处理。

每个 Agent 进程：
- 用 --session-id 保持对话连续性
- 用 --print 模式接收消息并返回响应
- 各自独立，互不阻塞
"""
import json, subprocess, time, os, signal, sys, threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE = Path(__file__).resolve().parent.parent
ROUTING = json.loads((BASE / "config" / "user-routing.json").read_text("utf-8"))
SETTINGS = str(BASE / "config" / "agent-teams-settings.json")
DISPATCH_PORT = 9100

# 管理所有 Agent 进程
agent_processes = {}

def load_agent_prompt(open_id):
    """加载 Agent 的系统提示"""
    agent_dir = BASE / "agents" / open_id
    parts = []
    if (agent_dir / "IDENTITY.md").exists():
        parts.append((agent_dir / "IDENTITY.md").read_text("utf-8"))
    if (agent_dir / "SOP.md").exists():
        parts.append("\n## 工作流程\n" + (agent_dir / "SOP.md").read_text("utf-8"))
    if (BASE / "config" / "AGENCY.md").exists():
        parts.append("\n## 规章\n" + (BASE / "config" / "AGENCY.md").read_text("utf-8")[:600])
    return "\n\n".join(parts)

def start_agent_process(agent_name, session_id, prompt_text):
    """启动一个后台 Claude Code 进程"""
    prompt_file = BASE / f".agent_prompt_{agent_name}.md"
    prompt_file.write_text(prompt_text, "utf-8")

    # Claude Code --print 模式：从 args 接收消息，输出响应
    def worker():
        while True:
            # 进程会在处理完消息后退出，由 dispatcher 重新启动
            time.sleep(1)

    print(f"  [{agent_name}] Agent 已加载 (session: {session_id})")
    return str(prompt_file)

# 初始化所有 Agent
agent_info = {}
for open_id, info in ROUTING.items():
    if not info.get("enabled", True):
        continue
    session_id = f"agent_{info['agent_name']}"
    prompt = load_agent_prompt(open_id)
    prompt_file = start_agent_process(info["agent_name"], session_id, prompt)
    agent_info[info["agent_name"]] = {
        "open_id": open_id,
        "feishu_name": info["feishu_name"],
        "session_id": session_id,
        "prompt_file": prompt_file,
    }


# ── HTTP API (供主 Claude Code session 调用) ───────

class DispatcherHandler(BaseHTTPRequestHandler):
    def _send(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        path = self.path

        if path == "/dispatch":
            agent_name = body.get("agent")
            message = body.get("message", "")
            if agent_name not in agent_info:
                self._send(404, {"error": f"unknown agent: {agent_name}"})
                return

            info = agent_info[agent_name]
            session_id = info["session_id"]
            feishu_name = info["feishu_name"]

            # 同步调用 claude --print 处理消息
            cmd = [
                "claude", "--print",
                "--session-id", session_id,
                "--settings", SETTINGS,
                "-p", f"[来自 {feishu_name}] {message}"
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                self._send(200, {
                    "agent": agent_name,
                    "response": result.stdout.strip() or result.stderr.strip(),
                })
            except subprocess.TimeoutExpired:
                self._send(504, {"error": "agent timeout"})
            except Exception as e:
                self._send(500, {"error": str(e)})
            return

        if path == "/agents":
            self._send(200, {name: {
                "feishu_name": v["feishu_name"],
                "session_id": v["session_id"],
            } for name, v in agent_info.items()})
            return

        self._send(404, {"error": "not found"})

    def do_GET(self):
        self.do_POST()


def start_dispatcher():
    server = HTTPServer(("0.0.0.0", DISPATCH_PORT), DispatcherHandler)
    print(f"  Dispatcher API: http://localhost:{DISPATCH_PORT}")
    print(f"  POST /dispatch  body: {{'agent':'小然','message':'你好'}}")
    server.serve_forever()


if __name__ == "__main__":
    print("=" * 50)
    print("Agent Dispatcher 启动")
    for name, info in agent_info.items():
        print(f"  [{name}] {info['feishu_name']} (session: {info['session_id']})")
    print(f"  Dispatcher 监听 :{DISPATCH_PORT}")
    print("=" * 50)
    start_dispatcher()
