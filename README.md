# Company AI Agent Teams

每个飞书员工拥有独立 AI 助手（Agent），通过 Claude Code Agent Teams 模式协作，额度可控。

## 快速启动

```bash
# 一键启动（代理 + 管理面板 + Agent Teams）
scripts\start.bat
```

启动后：
- **管理面板** → http://localhost:5000
- **额度代理** → http://localhost:8800

## 文件结构

```
company-agents/
├── config/
│   ├── feishu-app.json           # 飞书应用凭证
│   ├── user-routing.json         # 用户映射 + 额度
│   ├── agent-teams-settings.json # 模型/代理配置
│   └── AGENCY.md                 # 全局规章（数据隔离、协作规范）
├── agents/
│   ├── _template/                # 新用户模板
│   └── ou_{open_id}/             # 每个用户一个目录
│       ├── IDENTITY.md           # 角色/性格
│       ├── SOP.md                # 工作流程
│       └── memory/               # 个人记忆
├── proxy/proxy.py                # 额度代理（拦截 API + 计数 + 限流）
├── admin/
│   ├── app.py                    # 管理面板后端
│   └── templates/index.html      # 管理面板前端
├── scripts/
│   ├── start.bat                 # 一键启动
│   ├── launch_agents.py          # 构建 Agent Teams 并启动
│   └── register_agent.py         # 新用户注册模块
└── README.md
```

## 管理面板功能

| 标签页 | 功能 |
|--------|------|
| 用户管理 | 查看/编辑/启用/停用 Agent |
| 额度管理 | 查看用量进度条、重置月度计数 |
| 全局设置 | 调整默认月度 Token 上限、频率限制 |

## Agent Teams 成员

| Agent | 用户 | 角色 |
|-------|------|------|
| admin | 管理员 | 系统管理、跨 Agent 写入 |
| 小然 | 赵奕然 | 运营部 |
| 小敏 | 梁晓敏 | 人力资源部 |
| 小桐 | 王桐 | 运营部 |

## 添加新用户

用户第一次给飞书机器人发消息时，admin Agent 会自动引导完成注册问卷（姓名、角色、Agent 名称、技能、性格），生成 IDENTITY.md 并写入映射表。

也可手动注册：
```bash
cd company-agents
python -c "from scripts.register_agent import register_agent; register_agent('ou_xxx', '姓名', 'Agent名', '角色', '技能', '性格')"
```

## 额度规则

- 默认每人每月 500 万 Token，每分钟 10 次请求
- 超限后硬阻断，回复告知用户联系管理员
- 管理面板可单独调整某人额度或重置用量
- 新用户自动继承全局默认值

## Agent 间协作规则

- Agent 之间只读查询（互相询问信息）
- **写入**其他 Agent 的数据 → 必须通过 admin Agent
- 共享知识库（飞书 Wiki）所有 Agent 可读
- 个人 memory/ 仅自己可读写
