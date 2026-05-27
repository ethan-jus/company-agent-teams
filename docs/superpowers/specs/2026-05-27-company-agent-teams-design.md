# 公司 AI Agent Teams 系统设计

## 概述

基于 Claude Code Agent Teams + 飞书 MCP，为每个公司员工创建一个独立的 AI 个人助理。Agent 之间可互相协作，通过 Web 管理面板统一管理用户、额度和配置。

## 架构

```
飞书用户 ──私聊/群聊@──→ 飞书 MCP 插件 ←→ Claude Code CLI (Agent Teams 模式)
                                  │
                          ┌───────┴───────┐
                          │  Agent Team    │
                          │  ├── 小凌      │  (张三的 Agent)
                          │  ├── 小云      │  (李四的 Agent)
                          │  ├── ...       │
                          │  └── admin     │  (管理 Agent)
                          └───────┬───────┘
                                  │
                          ┌───────┴───────┐
                          │  额度代理层    │
                          │  (Python)      │
                          └───────┬───────┘
                                  │
                          DeepSeek API (共享 Key)
                                  │
                          ┌───────┴───────┐
                          │  Web 管理面板   │
                          │  Flask + SQLite │
                          └───────────────┘
```

### 组件职责

| 组件 | 技术 | 职责 |
|------|------|------|
| Claude Code CLI | Agent Teams 模式 | 核心 AI 处理，Agent 间协作 |
| 额度代理层 | Python | 透明拦截 API 请求，按 Agent 计数限流 |
| Web 管理面板 | Flask + SQLite | 用户/额度/日志管理 |
| 飞书 MCP | lark-* 系列工具 | 消息收发、文档操作、知识库查询 |

## 部署环境

- **操作系统**: Windows 11（原生，无需 WSL2）
- **运行时**: Node.js 22+、Python 3.10+
- **API**: DeepSeek API（共享 Key）
- **数据库**: SQLite（零运维）

## 路由与注册

### 消息路由流程

1. 飞书用户发送消息到机器人
2. 提取消息中的 `sender.open_id`
3. 查询 `user-routing.json` 映射表
4. **已注册**: 路由到对应用户的 Agent Team 成员
5. **未注册**: 触发自动注册流程

### 自动注册流程

1. 系统通过 `lark-contact` 按 `open_id` 反查用户飞书姓名
2. 发送欢迎消息，确认姓名："确认你的名字是『张三』对吗？"
3. 引导用户填写问卷：
   - 你希望 Agent 叫什么名字？（如"小凌"）
   - 你的角色/岗位是什么？
   - 你的核心技能/工作领域？
   - 你希望 Agent 的性格特点？
4. 生成 `IDENTITY.md` + `memory/` 目录
5. 写入 `user-routing.json` 映射表
6. 设定默认额度
7. Agent 加入 Team，注册完成

### 映射表结构

```json
{
  "ou_xxxxxxxxxx1": {
    "feishu_name": "张三",
    "agent_name": "小凌",
    "role": "运营总监",
    "open_id": "ou_xxxxxxxxxx1",
    "enabled": true,
    "quota": {
      "monthly_tokens": 5000000,
      "rate_per_minute": 10
    },
    "created_at": "2026-05-27T10:00:00Z",
    "agent_dir": "agents/ou_xxxxxxxxxx1/"
  }
}
```

## 额度控制

### 工作原理

- 额度代理层作为反向代理运行在 `localhost:8800`
- Claude Code 配置为通过该代理访问 DeepSeek API
- 代理根据请求来源 Agent 的身份（自定义 header）进行计数
- 数据持久化到 SQLite

### 限制类型

| 类型 | 默认值 | 行为 |
|------|--------|------|
| 月度 Token 上限 | 500 万 | HTTP 429 + 飞书提示 |
| 每分钟请求数 | 10 次 | HTTP 429 + 等待 |
| 单日 Token 告警 | 40 万 | 飞书推送告警（不阻断） |

### 可配置项

- 全局默认额度（新用户自动继承）
- 每人单独调整
- 月度手动重置

## Agent 独立性

每个用户拥有完全独立的 Agent 环境：

```
agents/
└── ou_xxxxxxxxxx1/
    ├── IDENTITY.md      # 性格/角色/技能/知识库
    └── memory/          # 个人记忆文件（对话历史+关键信息）
```

- **记忆**: 每个 Agent 维护自己的记忆文件，其他 Agent 只读
- **知识库**: 共享公司知识库（飞书 Wiki）所有 Agent 可读；个人知识库仅自己可读写
- **性格**: 通过 IDENTITY.md 定义，各 Agent 独立

## Agent 间协作

基于 Claude Code Agent Teams 原生的 Agent 间委托机制：

- Agent A 可以向 Agent B 发送任务请求
- 个人记忆跨 Agent **只读不可写**
- Agent 通信走 Agent Teams 内部协议，无需额外开发

## Web 管理面板

### 技术栈
- 后端: Python Flask
- 前端: 纯 HTML + CSS + JS（单页应用，无构建）
- 数据库: SQLite

### 功能

**用户管理**
- 用户列表（飞书姓名 | Agent 名称 | 角色 | open_id | 状态）
- 编辑用户资料
- 手动新增用户
- 启用/停用 Agent

**额度管理**
- 全局默认额度配置
- 每人用量进度条视图
- 月度重置
- 单独调整某人额度

**日志查看**
- 注册记录时间线
- Agent 协作记录
- 额度告警历史

## 目录结构

```
~/company-agents/
├── agents/
│   └── ou_xxxx1/
│       ├── IDENTITY.md
│       └── memory/
├── config/
│   ├── user-routing.json
│   ├── quota-defaults.json
│   └── feishu-app.json
├── proxy/
│   ├── proxy.py
│   └── quota.db
├── admin/
│   ├── app.py
│   └── templates/
│       └── index.html
├── scripts/
│   ├── start.bat
│   └── stop.bat
└── logs/
```

## 实施路线

| 步骤 | 内容 | 时间 |
|------|------|------|
| 1 | 项目目录 + 配置文件模板 | 半天 |
| 2 | 额度代理层（proxy.py） | 1天 |
| 3 | Agent Teams 配置 + 团队初始化 | 1天 |
| 4 | 自动注册流程 | 2天 |
| 5 | Web 管理面板 | 2天 |
| 6 | 飞书 MCP 集成 + 端到端测试 | 1天 |
| 7 | 内测 5 人 + 调优 | 持续 |

## 自审查清单

- [x] 无 TBD/占位符
- [x] 架构与功能描述一致
- [x] 范围聚焦（单个系统，未混入多项目）
- [x] 关键决策明确（WSL2 vs 原生、SQLite、Flask）
