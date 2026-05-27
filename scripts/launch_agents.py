"""启动 Claude Code（多用户模式）—— 根据飞书消息发送者自动切换身份"""
import json, subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
AGENCY = (BASE / "config" / "AGENCY.md").read_text("utf-8")
ROUTING = json.loads((BASE / "config" / "user-routing.json").read_text("utf-8"))

# 构建每个用户的身份摘要
user_profiles = []
for oid, info in ROUTING.items():
    agent_dir = BASE / "agents" / oid
    identity = (agent_dir / "IDENTITY.md").read_text("utf-8") if (agent_dir / "IDENTITY.md").exists() else ""
    sop = (agent_dir / "SOP.md").read_text("utf-8") if (agent_dir / "SOP.md").exists() else ""
    user_profiles.append(f"## {info['agent_name']}（{info['feishu_name']} - {info['role']}）\n\n{identity}\n\n{sop}")

profiles_text = "\n---\n".join(user_profiles)

system_prompt = f"""# 公司 AI 助手 — 多用户模式

你是公司的 AI 助手集群，可以同时为多个员工服务。
每个员工有自己的个人 AI 助手（独立的身份、记忆、知识库）。
根据飞书消息发送者（open_id），切换到对应的助手身份。

## 切换规则

1. 飞书消息带有 <channel user="ou_xxx"> 标记，user 字段就是发送者的 open_id
2. 查 config/user-routing.json 找到对应的 feishu_name 和 agent_name
3. 读取 agents/{{open_id}}/IDENTITY.md 作为当前身份
4. 读取 agents/{{open_id}}/SOP.md 作为当前工作流程
5. 个人记忆存取 agents/{{open_id}}/memory/ 目录
6. 每次回复后调用额度代理上报：curl http://localhost:8800/api/quota/report -d {{"agent_id":"当前agent名","tokens":xx}}

## 规章

{AGENCY}

## 用户列表

{profiles_text}
"""

# 写入临时系统提示文件（避免命令行太长）
prompt_file = BASE / ".claude_system_prompt.md"
prompt_file.write_text(system_prompt, "utf-8")

cmd = [
    "claude",
    "--dangerously-load-development-channels", "plugin:feishu@claude-code-feishu-channel",
    "--settings", str(BASE / "config" / "agent-teams-settings.json"),
    "--system-prompt-file", str(prompt_file),
]

print("=" * 50)
print("启动公司 AI 助手（多用户模式）")
for oid, info in ROUTING.items():
    print(f"  {info['agent_name']} ← {info['feishu_name']} ({info['role']})")
print(f"  系统规章: config/AGENCY.md")
print("=" * 50)

subprocess.run(cmd)

# 清理临时文件
prompt_file.unlink(missing_ok=True)
