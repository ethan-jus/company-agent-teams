"""启动 Agent Teams — admin 路由 + 各 Agent 独立并行处理"""
import json, subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
AGENCY = (BASE / "config" / "AGENCY.md").read_text("utf-8").strip()
ROUTING = json.loads((BASE / "config" / "user-routing.json").read_text("utf-8"))

agents = {}

# admin — 消息路由 + 系统管理
admin_routes = ""
for open_id, info in ROUTING.items():
    agent_dir = BASE / "agents" / open_id
    identity = (agent_dir / "IDENTITY.md").read_text("utf-8") if (agent_dir / "IDENTITY.md").exists() else ""
    sop = (agent_dir / "SOP.md").read_text("utf-8") if (agent_dir / "SOP.md").exists() else ""

    agents[info["agent_name"]] = {
        "description": f"{info['feishu_name']} 的个人助手 - {info['role']}",
        "prompt": f"""{identity}

你的 SOP：
{sop[:800]}

规章（必须遵守）：
{AGENCY[:600]}

协作方式：
- admin 用 @{info['agent_name']} 把飞书消息委托给你
- 处理完后用 reply 工具回复给飞书用户（chat_id 从消息中获取）
- 需要其他 Agent 信息时用 @Agent名 请求
- 跨 Agent 写入操作请 @admin 处理

额度上报：调用 POST /api/quota/report，body 传 {"agent_id": "{open_id}", "tokens": 本次消耗}
""",
    }
    admin_routes += f"- <channel user=\"{open_id}\" → {info['feishu_name']} → @{info['agent_name']}\n"

agents["admin"] = {
    "description": "系统管理员 / 消息路由",
    "prompt": f"""# admin — 飞书消息路由

收到飞书 channel 消息时：
1. 看 <channel user="ou_xxx"> 确定发送者
2. 查下面映射表，用 @Agent名 委托处理（使用 run_in_background: true 实现并行，多条消息可同时处理）
3. 例：赵奕然发来消息 → 用 background agent @"小然" 并传入 chat_id/message_id

## 用户 → Agent 映射
{admin_routes}

## 关键规则
⚠️ **必须使用 run_in_background: true 委托 Agent，不可串行等待！**
   - 收到消息 → 立刻后台启动对应 Agent → 继续处理下一条
   - 背景 Agent 自己拥有飞书 MCP 工具，可直接 reply 回复用户
   - 你会收到完成通知，无需主动轮询

## admin 亲自处理（串行，非后台）
- 新用户发消息 → 触发注册流程（需交互式问卷）
- 跨 Agent 写入 → admin 亲自处理
- 额度/配置管理 → admin 处理

## 规章
{AGENCY[:600]}
""",
}

cmd = [
    "claude",
    "--dangerously-load-development-channels", "plugin:feishu@claude-code-feishu-channel",
    "--settings", str(BASE / "config" / "agent-teams-settings.json"),
    "--agent", "admin",
    "--agents", json.dumps(agents, ensure_ascii=False),
]

print("=" * 50)
print("Agent Teams 启动，成员：")
for name, cfg in agents.items():
    print(f"  [{name}] {cfg['description']}")
print("  ──")
print("  admin 负责路由飞书消息 @各Agent")
print("  各Agent独立并行处理，可切换查看")
print("=" * 50)

subprocess.run(cmd)
