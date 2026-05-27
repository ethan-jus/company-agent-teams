"""启动 Agent Teams — 读取各 Agent 身份文件，生成 team 配置，启动 Claude Code"""
import json, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
AGENCY = (BASE / "config" / "AGENCY.md").read_text("utf-8").strip()
ROUTING = json.loads((BASE / "config" / "user-routing.json").read_text("utf-8"))

agents = {
    "admin": {
        "description": "系统管理员",
        "prompt": f"""你是 admin Agent，系统管理员。

职责：
- 管理用户注册（调用 scripts/register_agent.py）
- 检查/调整额度
- 处理跨 Agent 写入请求
- 监督所有 Agent 遵守规章

规章：
{AGENCY[:800]}""",
    }
}

for open_id, info in ROUTING.items():
    agent_dir = BASE / "agents" / open_id
    identity = (agent_dir / "IDENTITY.md").read_text("utf-8") if (agent_dir / "IDENTITY.md").exists() else ""
    sop = (agent_dir / "SOP.md").read_text("utf-8") if (agent_dir / "SOP.md").exists() else ""
    agents[info["agent_name"]] = {
        "description": f"{info['feishu_name']} 的个人助手 - {info['role']}",
        "prompt": f"""{identity}

你的 SOP：
{sop[:600]}

规章：
{AGENCY[:600]}
""",
    }

# 构建启动命令
cmd = [
    "claude",
    "--settings", str(BASE / "config" / "agent-teams-settings.json"),
    "--agents", json.dumps(agents, ensure_ascii=False),
]

print("=" * 50)
print("启动 Agent Teams，包含以下成员：")
for name, cfg in agents.items():
    print(f"  - {name}: {cfg['description']}")
print("=" * 50)

subprocess.run(cmd)
