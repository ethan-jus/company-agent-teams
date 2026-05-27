"""Launch Agent Teams - admin routes Feishu messages to user agents"""
import json, subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
AGENCY = (BASE / "config" / "AGENCY.md").read_text("utf-8").strip()
ROUTING = json.loads((BASE / "config" / "user-routing.json").read_text("utf-8"))

agents = {}
admin_routes = ""

for open_id, info in ROUTING.items():
    agent_dir = BASE / "agents" / open_id
    identity = (agent_dir / "IDENTITY.md").read_text("utf-8") if (agent_dir / "IDENTITY.md").exists() else ""
    sop = (agent_dir / "SOP.md").read_text("utf-8") if (agent_dir / "SOP.md").exists() else ""

    agents[info["agent_name"]] = {
        "description": f"{info['feishu_name']} - {info['role']}",
        "prompt": "\n".join([
            identity,
            "",
            "## Your SOP:",
            sop[:800],
            "",
            "## Rules:",
            AGENCY[:600],
            "",
            "## Collaboration:",
            "- admin uses @" + info["agent_name"] + " to delegate Feishu messages to you",
            "- Reply to users using the reply tool (chat_id comes from the message)",
            "- Request help from other agents using @AgentName",
            "- Cross-agent writes go through @admin",
            "- Report token usage after each reply: curl -s http://localhost:8800/api/quota/report -d '{\"agent_id\":\"" + open_id + "\",\"tokens\":0}'",
        ]),
    }
    admin_routes += f"- <channel user=\"{open_id}\" -> {info['feishu_name']} -> @{info['agent_name']}\n"

agents["admin"] = {
    "description": "System admin / message router",
    "prompt": "\n".join([
        "# admin - Feishu Message Router",
        "",
        "When a Feishu channel message arrives:",
        "1. Check <channel user=\"ou_xxx\"> for the sender's open_id",
        "2. Look up the mapping below and delegate using @AgentName",
        "3. Example: @xiaoran Please handle: [message]",
        "",
        "## User -> Agent Mapping",
        admin_routes,
        "",
        "## Key Rules",
        "- Delegate messages in parallel (run_in_background: true), don't wait for completion",
        "- Each agent has their own MCP tools and can reply directly via Feishu",
        "",
        "## Admin-only (serial, not background)",
        "- New user registration (interactive questionnaire)",
        "- Cross-agent data writes",
        "- Quota/config management",
        "",
        "## Rules:",
        AGENCY[:600],
    ]),
}

cmd = [
    "claude",
    "--dangerously-load-development-channels", "plugin:feishu@claude-code-feishu-channel",
    "--settings", str(BASE / "config" / "agent-teams-settings.json"),
    "--agent", "admin",
    "--agents", json.dumps(agents, ensure_ascii=False),
]

print("=" * 50)
print("Agent Teams started with members:")
for name, cfg in agents.items():
    print(f"  [{name}] {cfg['description']}")
print("  ---")
print("  admin routes Feishu messages @agents")
print("  Each agent processes independently")
print("=" * 50)

subprocess.run(cmd)
