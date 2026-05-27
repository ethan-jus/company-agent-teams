"""启动系统 — 后台 Dispatcher + 主 Claude Code（飞书消息路由）"""
import json, subprocess, threading, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ROUTING = json.loads((BASE / "config" / "user-routing.json").read_text("utf-8"))

# ── 1. 启动 Dispatcher（后台，管理各 Agent 进程）──
dispatcher = subprocess.Popen(
    ["C:/Python314/python.exe", str(BASE / "scripts" / "agent_dispatcher.py")],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
time.sleep(3)

# 读取 dispatcher 输出确认启动成功
line = dispatcher.stdout.readline() if dispatcher.stdout else ""
print(line)

# ── 2. 构建主 session 的系统提示 ──
user_list = "\n".join([
    f"  - <channel user=\"{oid}\"> → agent \"{info['agent_name']}\" ({info['feishu_name']} - {info['role']})"
    for oid, info in ROUTING.items() if info.get("enabled", True)
])

system_prompt = f"""# AI 助手消息路由器

你的职责只有一个：收到飞书消息后，转发给对应的 Agent 处理并回复。

## 工作流程

1. 收到飞书 channel 消息时，查看 <channel user="ou_xxx"> 的 open_id
2. 根据 open_id 确定对应的 agent 名称
3. 调用 Dispatcher API 处理（会并行执行，不阻塞）：
   curl -s http://localhost:9100/dispatch -H "Content-Type: application/json" -d '{{"agent":"AGENT名","message":"消息内容"}}'
4. 收到 API 返回的 response 后，用 reply 工具回复给飞书用户

## 用户映射
{user_list}

## 注意事项
- 不要自己处理用户的问题，直接转发给 Dispatcher API
- 每个用户的消息是独立并行的，不要等前一个处理完再发下一个
- 如果 Dispatcher 返回超时或错误，告知用户"系统繁忙，请稍后重试"
"""

prompt_file = BASE / ".claude_system_prompt.md"
prompt_file.write_text(system_prompt, "utf-8")

# ── 3. 启动主 Claude Code ──
cmd = [
    "claude",
    "--dangerously-load-development-channels", "plugin:feishu@claude-code-feishu-channel",
    "--settings", str(BASE / "config" / "agent-teams-settings.json"),
    "--system-prompt-file", str(prompt_file),
]

print("=" * 50)
print("系统启动完毕")
print(f"  Dispatcher -> http://localhost:9100 (管理 Agent 进程)")
print(f"  用户映射:")
for oid, info in ROUTING.items():
    if info.get("enabled", True):
        print(f"    {info['feishu_name']} → {info['agent_name']}")
print("=" * 50)

subprocess.run(cmd)

# 清理
prompt_file.unlink(missing_ok=True)
dispatcher.terminate()
