"""启动 Agent Teams — admin 路由飞书消息给对应 Agent"""
import json, subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
AGENCY = (BASE / "config" / "AGENCY.md").read_text("utf-8").strip()
ROUTING = json.loads((BASE / "config" / "user-routing.json").read_text("utf-8"))

agents = {}

# admin Agent — 消息路由 + 系统管理
agents["admin"] = {
    "description": "系统管理员 / 消息路由",
    "prompt": f"""# admin Agent — 系统管理员 & 消息路由

## 核心职责

### 1. 飞书消息路由（最重要）
当飞书消息通过 channel 到达时：
1. 查看 <channel user="ou_xxx"> 中的 open_id
2. 打开 config/user-routing.json 查对应用户
3. 用 @Agent名 将请求委托给对应用户的个人 Agent
4. 例如：赵奕然发来消息 → @"小然" 赵奕然说：...

### 2. 跨 Agent 写入
其他 Agent 需要修改配置或跨 Agent 数据时，由 admin 执行。

### 3. 用户注册
新用户发消息时，执行注册流程。

## 各 Agent 对应关系
""",
}

for open_id, info in ROUTING.items():
    agent_dir = BASE / "agents" / open_id
    identity = (agent_dir / "IDENTITY.md").read_text("utf-8") if (agent_dir / "IDENTITY.md").exists() else ""
    sop = (agent_dir / "SOP.md").read_text("utf-8") if (agent_dir / "SOP.md").exists() else ""

    agents[info["agent_name"]] = {
        "description": f"{info['feishu_name']} 的个人助手 - {info['role']}",
        "prompt": f"""{identity}

你的专属工作流程（SOP）：
{sop}

全局规章（必须遵守）：
{AGENCY[:800]}

## 协作方式
- 当 admin 用 @{info['agent_name']} 把任务委托给你时，处理该任务
- 处理完毕后直接回复（回复会自动通过飞书 channel 发送给用户）
- 如果需要其他 Agent 的信息，用 @Agent名 请求协作
- 需要写入其他 Agent 数据时，请 @admin 处理
""",
    }

    # 在 admin 的 prompt 中追加用户映射
    agents["admin"]["prompt"] += f"\n- <channel user=\"{open_id}\"> → @{info['agent_name']}（{info['feishu_name']}）"

agents["admin"]["prompt"] += f"""

## 路由规则
- 查不到 open_id 的用户 → 触发注册流程
- 跨 Agent 写入请求 → admin 亲自处理
- 其他管理操作（额度、配置） → admin 亲自处理

## 规章
{AGENCY[:800]}
"""

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
print("  └ admin 负责路由飞书消息 @对应Agent")
print("=" * 50)

subprocess.run(cmd)
