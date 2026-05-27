"""Agent 注册流程 — 为新飞书用户创建独立 Agent。

通过飞书用户问卷收集信息，从模板生成 IDENTITY.md，
更新 user-routing.json 映射表，完成注册。

用法:
  from scripts.register_agent import register_agent
  result = register_agent("ou_xxx", "张三", "小凌", "运营", "数据分析", "细致高效")
"""

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
    """为新用户注册一个独立 Agent"""
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8")) if ROUTING_PATH.exists() else {}
    if open_id in routing:
        return {"success": False, "message": f"用户 {feishu_name} 已注册"}

    # 创建 Agent 目录
    agent_dir = AGENTS_DIR / open_id
    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    # 从模板生成 IDENTITY.md
    template = (TEMPLATE_DIR / "IDENTITY.md").read_text(encoding="utf-8")
    identity = (
        template.replace("{{AGENT_NAME}}", agent_name)
        .replace("{{USER_NAME}}", feishu_name)
        .replace("{{USER_ROLE}}", role)
        .replace("{{USER_SKILLS}}", skills)
        .replace("{{PERSONALITY}}", personality)
        .replace("{{OPEN_ID}}", open_id)
    )
    (agent_dir / "IDENTITY.md").write_text(identity, encoding="utf-8")

    # 初始记忆
    (memory_dir / "about.md").write_text(
        f"# 关于 {feishu_name}\n\n"
        f"- 姓名：{feishu_name}\n"
        f"- 角色：{role}\n"
        f"- 技能：{skills}\n"
        f"- Agent 名称：{agent_name}\n"
        f"- 注册时间：{datetime.now().isoformat()}\n",
        encoding="utf-8",
    )

    # 读取默认额度
    defaults = json.loads(QUOTA_PATH.read_text(encoding="utf-8")) if QUOTA_PATH.exists() else {}

    # 更新路由映射
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

    return {"success": True, "message": f"Agent「{agent_name}」已为 {feishu_name} 创建"}


def unregister_agent(open_id):
    """注销 Agent，删除目录和映射"""
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    if open_id not in routing:
        return {"success": False, "message": "用户未注册"}
    agent_dir = AGENTS_DIR / open_id
    if agent_dir.exists():
        shutil.rmtree(agent_dir)
    del routing[open_id]
    ROUTING_PATH.write_text(json.dumps(routing, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "message": f"Agent {open_id} 已注销"}


def list_agents():
    """列出所有已注册 Agent"""
    return json.loads(ROUTING_PATH.read_text(encoding="utf-8")) if ROUTING_PATH.exists() else {}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        agents = list_agents()
        print(f"共 {len(agents)} 个 Agent:")
        for oid, info in agents.items():
            print(f"  {oid[:20]}... | {info.get('feishu_name','?')} | {info.get('agent_name','?')} | {info.get('role','?')}")
