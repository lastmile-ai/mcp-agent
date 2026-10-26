<p align="center">
  <a href="https://docs.mcp-agent.com"><img src="https://github.com/user-attachments/assets/c8d059e5-bd56-4ea2-a72d-807fb4897bde" alt="Logo" width="300" /></a>
</p>

<p align="center">
  <em>使用简洁、可组合的模式，基于模型上下文协议（Model Context Protocol, MCP）构建高效的智能体。</em>

<p align="center">
  <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples" target="_blank"><strong>示例项目</strong></a>
  |
  <a href="https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/overview" target="_blank"><strong>构建高效智能体</strong></a>
  |
  <a href="https://modelcontextprotocol.io/introduction" target="_blank"><strong>MCP 协议</strong></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b>
</p>

<p align="center">
<a href="https://docs.mcp-agent.com"><img src="https://img.shields.io/badge/docs-8F?style=flat&link=https%3A%2F%2Fdocs.mcp-agent.com%2F" /><a/>
<a href="https://pypi.org/project/mcp-agent/"><img src="https://img.shields.io/pypi/v/mcp-agent?color=%2334D058&label=pypi" /></a>
<img alt="Pepy Total Downloads" src="https://img.shields.io/pepy/dt/mcp-agent?label=pypi%20%7C%20downloads"/>
<a href="https://github.com/lastmile-ai/mcp-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"/></a>
<a href="https://lmai.link/discord/mcp-agent"><img src="https://img.shields.io/badge/Discord-%235865F2.svg?logo=discord&logoColor=white" alt="discord"/></a>
</p>

<p align="center">
<a href="https://trendshift.io/repositories/13216" target="_blank"><img src="https://trendshift.io/api/badge/repositories/13216" alt="lastmile-ai%2Fmcp-agent | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
</p>

## 概述

**`mcp-agent`** 是一个简洁、可组合的框架，用于基于[模型上下文协议（Model Context Protocol, MCP）](https://modelcontextprotocol.io/introduction)构建高效的智能体（Agents）。

> [!Note]
> mcp-agent 的核心愿景是：_构建智能体只需 MCP 就够了；在交付高质量智能体时，简洁可组合的模式比复杂的架构更加稳健可靠_。

`mcp-agent` 为您提供以下核心能力：

1. **完整的 MCP 支持**：它_完整_实现了 MCP 协议，并为您妥善处理了管理 MCP 服务器连接生命周期等繁琐事务，让您无需为此费心。
2. **高效的智能体模式**：它以_可组合（Composable）_的方式实现了 Anthropic 在 [《Building Effective Agents》](https://www.anthropic.com/engineering/building-effective-agents) 中阐述的每一种模式，允许您将这些模式灵活串联与组合。
3. **持久化智能体（Durable agents）**：它既适用于轻量级简单智能体，也能无缝扩展至基于 [Temporal](https://temporal.io/) 构建的复杂生产级工作流，使您无需修改智能体的任何 API 代码即可实现暂停、恢复与故障自愈。

<u>总而言之，这是构建稳健智能体应用最简单、最省心的方式</u>。

我们热忱欢迎各种形式的[贡献](/CONTRIBUTING.md)、反馈以及您对改进本项目的帮助。

<a id="minimal-example"></a>
**最简示例**

```python
import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="hello_world")

async def main():
    async with app.run():
        agent = Agent(
            name="finder",
            instruction="Use filesystem and fetch to answer questions.",
            server_names=["filesystem", "fetch"],
        )
        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)
            answer = await llm.generate_str("Summarize README.md in two sentences.")
            print(answer)


if __name__ == "__main__":
    asyncio.run(main())

# 请将您的 LLM API 密钥添加至 `mcp_agent.secrets.yaml` 或设置在环境变量中。
# [快速入门指南](https://docs.mcp-agent.com/get-started/overview) 详细介绍了配置与密钥管理步骤。

```

## 核心亮点一览

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>构建智能体</h3>
      <p>通过简洁、可组合的模式（如 Map-Reduce、编排器 Orchestrator、评估-优化器 Evaluator-Optimizer、路由器 Router 等）将大语言模型连接到 MCP 服务器。</p>
      <p>
        <a href="https://docs.mcp-agent.com/get-started/overview">快速开始 ↗</a> |
        <a href="https://docs.mcp-agent.com/mcp-agent-sdk/overview">文档 ↗</a>
      </p>
    </td>
    <td width="50%" valign="top">
      <h3>创建任意类型的 MCP 服务器</h3>
      <p>使用兼容 FastMCP 的 API 创建 MCP 服务器。您甚至可以将智能体本身直接暴露为 MCP 服务器。</p>
      <p>
        <a href="https://docs.mcp-agent.com/mcp-agent-sdk/mcp/agent-as-mcp-server">MCP 智能体服务器 ↗</a> |
        <a href="https://docs.mcp-agent.com/cloud/use-cases/deploy-chatgpt-apps">🎨 构建 ChatGPT 应用 ↗</a> |
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/mcp_agent_server">示例 ↗</a>
      </p>
    </td>
  </tr>
    <tr>
    <td width="50%" valign="top">
      <h3>完整的 MCP 支持</h3>
      <p><b>核心能力：</b> 工具 (Tools) ✅ 资源 (Resources) ✅ 提示词 (Prompts) ✅ 通知 (Notifications) ✅<br/>
      <b>高级特性：</b> OAuth ✅ 采样 (Sampling) ✅ 引导询问 (Elicitation) ✅ 根目录 (Roots) ✅</p>
      <p>
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/mcp">示例 ↗</a> |
        <a href="https://modelcontextprotocol.io/docs/getting-started/intro">MCP 文档 ↗</a>
      </p>
    </td>
    <td width="50%" valign="top">
      <h3>持久化执行 (Temporal)</h3>
      <p>使用 Temporal 作为智能体运行时后端，<i>无需修改任何 API 代码</i>即可横向扩展至生产级工作负载。</p>
      <p>
        <a href="https://docs.mcp-agent.com/mcp-agent-sdk/advanced/durable-agents">文档 ↗</a> |
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/temporal">示例 ↗</a>
      </p>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>☁️ 部署至云端</h3>
      <p><b>Beta：</b> 既可自行部署智能体，也可使用 <b>mcp-c</b> 托管智能体运行时。所有应用均作为标准 MCP 服务器进行部署。</p>
      <p>
        <a href="https://www.youtube.com/watch?v=0C4VY-3IVNU">演示视频 ↗</a> |
        <a href="https://docs.mcp-agent.com/get-started/cloud">云端快速开始 ↗</a> |
        <a href="https://github.com/lastmile-ai/mcp-agent/tree/main/examples/cloud">示例 ↗</a>
      </p>
    </td>
  </tr>
</table>

## 文档与使用 LLM 构建

mcp-agent 的完整文档托管于 **[docs.mcp-agent.com](https://docs.mcp-agent.com)**，包含完整的 SDK 指南、CLI 参考手册以及高级模式详解。本 README 旨在为您提供高屋建瓴的概览以助您快速上手。

- [`llms-full.txt`](https://docs.mcp-agent.com/llms-full.txt)：包含完整的全量文档内容。
- [`llms.txt`](https://docs.mcp-agent.com/llms.txt)：列出文档关键页面的站点地图（Sitemap）。
- [文档 MCP 服务器](https://docs.mcp-agent.com/mcp)

## 目录

- [概述](#概述)
- [最简示例](#minimal-example)
- [快速开始](#快速开始)
- [为什么选择 mcp-agent](#为什么选择-mcp-agent)
- [核心组件](#核心组件)
  - [MCPApp](#mcpapp)
  - [Agents 与 AgentSpec](#agents-与-agentspec)
  - [增强型 LLM (Augmented LLM)](#增强型-llm-augmented-llm)
  - [工作流与装饰器](#工作流与装饰器)
  - [配置与密钥管理](#配置与密钥管理)
  - [MCP 集成](#mcp-集成)
- [工作流模式](#工作流模式)
- [CLI 参考](#cli-参考)
- [身份认证](#身份认证)
- [高级特性](#高级特性)
  - [可观测性与控制](#可观测性与控制)
  - [组合工作流](#组合工作流)
  - [持久化执行](#持久化执行)
  - [智能体服务器](#智能体服务器)
  - [信号与人工输入 (Human-in-the-loop)](#信号与人工输入-human-in-the-loop)
  - [应用配置](#应用配置)
  - [图标 (Icons)](#图标-icons)
  - [MCP 服务器管理](#mcp-服务器管理)
- [云端部署](#云端部署)
- [示例项目](#示例项目)
- [常见问题 (FAQs)](#常见问题-faqs)
- [社区与贡献](#参与贡献)

## 快速开始

> [!TIP]
> CLI 工具可通过 `uvx mcp-agent` 直接使用。
> 如需快速启动并运行，可使用 `uvx mcp-agent init` 初始化项目脚手架，并通过 `uvx mcp-agent deploy my-agent` 一键部署。
>
> 您只需运行以下命令，即可在 2 分钟内启动并运行：
>
> ```bash
> mkdir hello-mcp-agent && cd hello-mcp-agent
> uvx mcp-agent init
> uv init
> uv add "mcp-agent[openai]"
> # 将 OpenAI API 密钥添加到 `mcp_agent.secrets.yaml` 或设置 `OPENAI_API_KEY` 环境变量
> uv run main.py
> ```

### 安装

我们推荐使用 [uv](https://docs.astral.sh/uv/) 来管理您的 Python 项目（`uv init`）。

```bash
uv add "mcp-agent"
```

或者使用 `pip`：

```bash
pip install mcp-agent
```

您还可以按需安装对应大语言模型提供商的可选依赖包（例如：`uv add "mcp-agent[openai, anthropic, google, azure, bedrock]"`）。

### 快速上手示例

> [!TIP]
> [`examples`](/examples) 目录中提供了多个可直接运行的示例应用。
> 如需运行示例，请克隆本仓库（或使用 `uvx mcp-agent init --template basic --dir my-first-agent` 生成项目）：
>
> ```bash
> cd examples/basic/mcp_basic_agent # 或进入任意其他示例目录
> # 方式 A：通过 secrets YAML 配置密钥
> # cp mcp_agent.secrets.yaml.example mcp_agent.secrets.yaml && edit mcp_agent.secrets.yaml
> uv run main.py
> ```

下面是一个基础的“finder”智能体示例，它使用 `fetch` 和 `filesystem` 服务器来查找本地文件、读取技术博客并撰写一条推文。[示例链接](./examples/basic/mcp_basic_agent/)：

<details open>
<summary>finder_agent.py</summary>

```python
import asyncio
import os

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

app = MCPApp(name="hello_world_agent")

async def example_usage():
    async with app.run() as mcp_agent_app:
        logger = mcp_agent_app.logger
        # 该智能体可以读取本地文件系统或抓取网页 URL
        finder_agent = Agent(
            name="finder",
            instruction="""You can read local files or fetch URLs.
                Return the requested information when asked.""",
            server_names=["fetch", "filesystem"], # 该智能体可使用的 MCP 服务器列表
        )

        async with finder_agent:
            # 自动初始化 MCP 服务器并将其工具注册供 LLM 调用
            tools = await finder_agent.list_tools()
            logger.info(f"Tools available:", data=tools)

            # 为智能体挂载 OpenAI LLM（默认使用 GPT-4o）
            llm = await finder_agent.attach_llm(OpenAIAugmentedLLM)

            # 通过 filesystem 服务器执行本地文件查找与读取
            result = await llm.generate_str(
                message="Show me what's in README.md verbatim"
            )
            logger.info(f"README.md contents: {result}")

            # 使用 fetch 服务器从指定 URL 抓取网页内容
            result = await llm.generate_str(
                message="Print the first two paragraphs from https://www.anthropic.com/research/building-effective-agents"
            )
            logger.info(f"Blog intro: {result}")

            # 默认支持多轮对话交互
            result = await llm.generate_str("Summarize that in a 128-char tweet")
            logger.info(f"Tweet: {result}")

if __name__ == "__main__":
    asyncio.run(example_usage())

```

</details>

<details>
<summary>mcp_agent.config.yaml</summary>

```yaml
execution_engine: asyncio
logger:
  transports: [console] # 您可以使用 [file, console] 同时输出到文件与控制台
  level: debug
  path: "logs/mcp-agent.jsonl" # 用于 file 传输模式
  # 如需使用动态日志文件名：
  # path_settings:
  #   path_pattern: "logs/mcp-agent-{unique_id}.jsonl"
  #   unique_id: "timestamp"  # 或 "session_id"
  #   timestamp_format: "%Y%m%d_%H%M%S"

mcp:
  servers:
    fetch:
      command: "uvx"
      args: ["mcp-server-fetch"]
    filesystem:
      command: "npx"
      args:
        [
          "-y",
          "@modelcontextprotocol/server-filesystem",
          "<add_your_directories>",
        ]

openai:
  # 敏感密钥（API keys 等）存储在可被 gitignore 忽略的 mcp_agent.secrets.yaml 文件中
  default_model: gpt-4o
```

</details>

<details>
<summary>智能体运行输出</summary>
<img width="2398" alt="Image" src="https://github.com/user-attachments/assets/eaa60fdf-bcc6-460b-926e-6fa8534e9089" />
</details>

## 为什么选择 `mcp-agent`？

市面上的 AI 框架已经数不胜数，但 `mcp-agent` 是唯一一个专为统一共享协议——[MCP](https://modelcontextprotocol.io/introduction) 而原生设计的框架。[mcp-agent](https://docs.mcp-agent.com/get-started/welcome) 将 Anthropic 的《构建高效智能体（Building Effective Agents）》模式与开箱即用的 MCP 运行时深度结合，让您专注于智能体行为本身，而非样板代码。众多工程团队选择它的原因在于：

- **可组合（Composable）** —— 每一种模式都封装为可复用的工作流，支持自由混搭与嵌套。
- **MCP 原生（MCP-native）** —— 任何 MCP 服务器（如 filesystem、fetch、Slack、Jira、FastMCP 应用）无需编写自定义适配器即可直接接入。
- **生产就绪（Production ready）** —— 一等公民级支持基于 Temporal 的持久化执行、结构化日志、Token 用量统计以及云端一键部署。
- **Pythonic 设计** —— 仅需几个简洁的装饰器与上下文管理器即可将所有组件优雅串联。

参考文档：[欢迎使用 mcp-agent](https://docs.mcp-agent.com/get-started/welcome) • [高效模式总览](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/overview)。

## 核心组件

每个项目都围绕单一的 `MCPApp` 运行时展开，由其统一负责加载配置、注册智能体与 MCP 服务器，并暴露工具与工作流。[核心组件指南](https://docs.mcp-agent.com/mcp-agent-sdk/overview)详细介绍了这些基础构建块。

### MCPApp

初始化全局配置、日志系统、链路追踪与执行引擎，使所有组件共享同一个上下文。

```python
from mcp_agent.app import MCPApp

app = MCPApp(name="finder_app")

async def main():
    async with app.run() as running_app:
        logger = running_app.logger
        logger.info("App ready", data={"servers": list(running_app.context.server_registry.registry)})
```

参考文档：[MCPApp](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/mcpapp) • 示例：[`examples/basic/mcp_basic_agent`](./examples/basic/mcp_basic_agent/)。

### Agents 与 AgentSpec

`Agent` 将指令（Instruction）与其允许调用的 MCP 服务器（及可选的本地函数）绑定在一起。`AgentSpec` 声明式定义可从磁盘加载，并通过工厂辅助函数直接转换为智能体或增强型 LLM（Augmented LLM）。

```python
from pathlib import Path
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.factory import load_agent_specs_from_file

agent = Agent(
    name="researcher",
    instruction="Research topics using web and filesystem access",
    server_names=["fetch", "filesystem"],
)

async with agent:
    tools = await agent.list_tools()

async with app.run() as running_app:
    specs = load_agent_specs_from_file(
        str(Path("examples/basic/agent_factory/agents.yaml")),
        context=running_app.context,
    )
```

参考文档：[Agents](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/agents) • [Agent 工厂辅助函数](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/agents#agentspec-and-factory-helpers) • 示例：[`examples/basic/agent_factory`](./examples/basic/agent_factory/)。

### 增强型 LLM (Augmented LLM)

增强型 LLM（Augmented LLM）在各模型提供商 SDK 的基础上封装了智能体的工具调用、记忆管理以及结构化输出辅助方法。将其挂载到智能体上即可解锁 `generate`、`generate_str` 与 `generate_structured` 方法。

```python
from pydantic import BaseModel
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

class Summary(BaseModel):
    title: str
    verdict: str

async with agent:
    llm = await agent.attach_llm(OpenAIAugmentedLLM)
    report = await llm.generate_str(
        message="Draft a 3-sentence release note from CHANGELOG.md",
        request_params=RequestParams(maxTokens=400, temperature=0.2),
    )
    structured = await llm.generate_structured(
        message="Return a JSON object with `title` and `verdict` summarising the README.",
        response_model=Summary,
    )
```

参考文档：[Augmented LLMs](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/augmented-llm) • 示例：[`examples/basic/mcp_basic_agent`](./examples/basic/mcp_basic_agent/) 以及 [gallery.md](gallery.md#workflow-patterns) 中列出的工作流项目。

### 工作流与装饰器

`MCPApp` 装饰器可将协程（Coroutines）直接转换为持久化工作流与工具。同一套注解同时兼容 `asyncio` 与 Temporal 执行引擎。

```python
from datetime import timedelta
from mcp_agent.executor.workflow import Workflow, WorkflowResult

@app.workflow
class PublishArticle(Workflow[WorkflowResult[str]]):
    @app.workflow_task(schedule_to_close_timeout=timedelta(minutes=5))
    async def draft(self, topic: str) -> str:
        return f"- intro to {topic}\n- highlights\n- next steps"

    @app.workflow_run
    async def run(self, topic: str) -> WorkflowResult[str]:
        outline = await self.draft(topic)
        return WorkflowResult(value=outline)
```

参考文档：[装饰器参考手册](https://docs.mcp-agent.com/reference/decorators) • 示例：[`examples/workflows`](./examples/workflows/)。

### 配置与密钥管理

配置信息支持从 `mcp_agent.config.yaml`、`mcp_agent.secrets.yaml`、环境变量以及可选的预加载字符串中读取。请务必将敏感密钥排除在版本控制之外。

```yaml
# mcp_agent.config.yaml
execution_engine: asyncio
mcp:
  servers:
    fetch:
      command: "uvx"
      args: ["mcp-server-fetch"]
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem"]
openai:
  default_model: gpt-4o-mini

# mcp_agent.secrets.yaml (已加入 gitignore)
openai:
  api_key: "${OPENAI_API_KEY}"
```

参考文档：[配置参考手册](https://docs.mcp-agent.com/reference/configuration) • [配置密钥指南](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/specify-secrets)。

### MCP 集成

通过编程方式直接连接到现有的 MCP 服务器，或将多个服务器聚合为统一的门面（Façade）。

```python
from mcp_agent.mcp.gen_client import gen_client

async with app.run():
    async with gen_client("filesystem", app.server_registry, context=app.context) as client:
        resources = await client.list_resources()
        app.logger.info("Filesystem resources", data={"uris": [r.uri for r in resources.resources]})
```

参考文档：[MCP 集成概览](https://docs.mcp-agent.com/mcp/overview) • 示例：[`examples/mcp`](./examples/mcp/)。

## 工作流模式

所有核心智能体模式均实现为 `AugmentedLLM` 的子类。您可以使用工厂辅助函数快速组装它们，或查看 [gallery.md](gallery.md#workflow-patterns) 中列出的可运行项目。

| 模式 | 辅助函数 | 简介 | 文档 |
| --------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| 并行处理 (Map-Reduce) | `create_parallel_llm(...)` | 扇出（Fan-out）分发给多个专家智能体，再扇入（Fan-in）汇总报告。<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png&w=3840&q=75" width="260"/></a> | [Parallel](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/map-reduce) |
| 路由器 (Router) | `create_router_llm(...)` / `create_router_embedding(...)` | 将请求智能路由至最合适的智能体、MCP 服务器或本地函数。<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F5c0c0e9fe4def0b584c04d37849941da55e5e71c-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F5c0c0e9fe4def0b584c04d37849941da55e5e71c-2401x1000.png&w=3840&q=75" width="260"/></a> | [Router](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/router) |
| 意图分类器 (Intent classifier) | `create_intent_classifier_llm(...)` / `create_intent_classifier_embedding(...)` | 在执行自动化流程前，将用户输入精准归类到特定意图。 | [Intent classifier](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/intent-classifier) |
| 编排器-工作者 (Orchestrator-workers) | `create_orchestrator(...)` | 动态生成执行计划并协调多个 Worker 智能体协同完成。<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F8985fc683fae4780fb34eab1365ab78c7e51bc8e-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F8985fc683fae4780fb34eab1365ab78c7e51bc8e-2401x1000.png&w=3840&q=75" width="260"/></a> | [Planner](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/planner) |
| 深度研究 (Deep research) | `create_deep_orchestrator(...)` | 具备知识提取与策略检查能力的长周期深度研究工作流。 | [Deep research](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/deep-research) |
| 评估-优化器 (Evaluator-optimizer) | `create_evaluator_optimizer_llm(...)` | 循环迭代优化生成结果，直至评估器（Evaluator）审核通过。<br><a href="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png&w=3840&q=75"><img src="https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png&w=3840&q=75" width="260"/></a> | [Evaluator-optimizer](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/evaluator-optimizer) |
| 群体协作 (Swarm) | `create_swarm(...)` | 兼容 OpenAI Swarm 风格的多智能体动态交接（Handoffs）。<br><a href="https://github.com/openai/swarm/blob/main/assets/swarm_diagram.png?raw=true"><img src="https://github.com/openai/swarm/blob/main/assets/swarm_diagram.png?raw=true" width="220"/></a> | [Swarm](https://docs.mcp-agent.com/mcp-agent-sdk/effective-patterns/swarm) |

## 持久化执行

只需将 `execution_engine` 切换为 `temporal`，即可在不修改任何工作流代码的前提下获得暂停/恢复、失败自动重试、人工审批输入以及持久化执行历史记录等能力。只需在应用旁启动一个 Worker 进程来托管活动（Activities）即可：

```python
from mcp_agent.executor.temporal import create_temporal_worker_for_app

async with create_temporal_worker_for_app(app) as worker:
    await worker.run()
```

参考文档：[持久化智能体](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/durable-agents) • [Temporal 后端](https://docs.mcp-agent.com/advanced/temporal) • 示例：[`examples/temporal`](./examples/temporal/)。

## 智能体服务器

将 `MCPApp` 直接暴露为标准的 MCP 服务器，从而让 Claude Desktop、Cursor 或自定义客户端能够直接调用您的智能体工具与工作流。

```python
from mcp_agent.server import create_mcp_server_for_app

@app.tool
def grade_story(story: str) -> str:
    return "Report..."

if __name__ == "__main__":
    server = create_mcp_server_for_app(app)
    server.run_stdio()
```

参考文档：[智能体服务器](https://docs.mcp-agent.com/mcp-agent-sdk/mcp/agent-as-mcp-server) • 示例：[`examples/mcp_agent_server`](./examples/mcp_agent_server/)。

## CLI 参考

`uvx mcp-agent` 支持快速生成项目脚手架、管理密钥、检查工作流以及一键部署至云端。

```bash
uvx mcp-agent init --template basic             # 生成新项目脚手架
uvx mcp-agent deploy my-agent                   # 部署至 mcp-agent Cloud
```

参考文档：[CLI 参考手册](https://docs.mcp-agent.com/reference/cli) • [快速入门指南](https://docs.mcp-agent.com/get-started/quickstart)。

## 身份认证

支持从密钥配置文件加载 API Key，或使用内置的 OAuth 客户端为 MCP 服务器自动获取并持久化访问令牌（Tokens）。

```yaml
# mcp_agent.config.yaml 片段
oauth:
  providers:
    github:
      client_id: "${GITHUB_CLIENT_ID}"
      client_secret: "${GITHUB_CLIENT_SECRET}"
      scopes: ["repo", "user"]
```

参考文档：[高级身份认证](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/authentication) • [服务器身份认证](https://docs.mcp-agent.com/mcp-agent-sdk/mcp/server-authentication) • 示例：[`examples/basic/oauth_basic_agent`](./examples/basic/oauth_basic_agent/)。

## 高级特性

### 可观测性与控制

通过配置文件即可开启结构化日志与 OpenTelemetry 链路追踪，并支持以编程方式实时统计 Token 消耗。

```yaml
# mcp_agent.config.yaml
logger:
  transports: [console]
  level: info
otel:
  enabled: true
  exporters:
    - console
```

`TokenCounter` 可自动追踪智能体、工作流及各个 LLM 节点的 Token 消耗情况。您可以挂载监听器（Watchers）以流式获取更新或触发预算告警：

```python
# 在 `async with app.run() as running_app:` 内部使用
# 当启用 tracing 时，token_counter 会挂载在运行中的应用上下文中。
token_counter = running_app.context.token_counter

class TokenMonitor:
    async def on_token_update(self, node, usage):
        print(f"[{node.name}] total={usage.total_tokens}")

monitor = TokenMonitor()
watch_id = await token_counter.watch(
    callback=monitor.on_token_update,
    node_type="llm",
    threshold=1_000,
    include_subtree=True,
)

await token_counter.unwatch(watch_id)
```

参考文档：[可观测性](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/observability) • 示例：[`examples/tracing`](./examples/tracing/)。

### 组合工作流

借助工厂辅助函数，您可以将多个 `AgentSpec` 自由混搭，构建出更高级的复合工作流——如路由器、并行流水线、编排器等。

```python
from mcp_agent.workflows.factory import create_router_llm

# specs 如前文所示通过 load_agent_specs_from_file 加载。
async with app.run() as running_app:
    router = await create_router_llm(
        agents=specs,
        provider="openai",
        context=running_app.context,
    )
```

参考文档：[工作流组合](https://docs.mcp-agent.com/mcp-agent-sdk/advanced/composition) • 示例：[`examples/basic/agent_factory`](./examples/basic/agent_factory/)。

### 信号与人工输入 (Human-in-the-loop)

工作流可在运行途中暂停，等待人工审批或补充信息。Temporal 会持久保存当前状态，直至操作员恢复运行。

```python
from mcp_agent.human_input.types import HumanInputRequest

response = await self.context.request_human_input(
    HumanInputRequest(
        prompt="Approve the draft?",
        required=True,
        metadata={"workflow_id": self.context.workflow_id},
    )
)
```

使用 `mcp-agent cloud workflows resume … --payload '{"content": "approve"}'` 恢复执行。参考文档：[部署智能体 – 人工输入模式](https://docs.mcp-agent.com/cloud/use-cases/deploy-agents#human-in-the-loop-patterns) • 示例：[`examples/human_input/temporal`](./examples/human_input/temporal/)。

### 应用配置

当您需要动态配置（如单元测试、多租户宿主环境）而非静态 YAML 文件时，可以直接通过编程方式构建 `Settings` 对象：

```python
from mcp_agent.config import Settings, MCPSettings, MCPServerSettings

settings = Settings(
    execution_engine="asyncio",
    mcp=MCPSettings(
        servers={
            "fetch": MCPServerSettings(command="uvx", args=["mcp-server-fetch"]),
        }
    ),
)
app = MCPApp(name="configured_app", settings=settings)
```

参考文档：[配置您的应用程序](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/configuring-your-application)。

### 图标 (Icons)

为智能体与工具添加自定义图标，使支持图像展示的 MCP 客户端（如 Claude Desktop、Cursor）能够渲染出更丰富的交互界面。

```python
from base64 import standard_b64encode
from pathlib import Path
from mcp_agent.icons import Icon

icon_data = standard_b64encode(Path("my-icon.png").read_bytes()).decode()
icon = Icon(src=f"data:image/png;base64,{icon_data}", mimeType="image/png", sizes=["64x64"])

app = MCPApp(name="my_app_with_icon", icons=[icon])

@app.tool(icons=[icon])
async def my_tool() -> str:
    return "Hello with style"
```

参考文档：[`MCPApp` 图标](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/mcpapp#icons) • 示例：[`examples/mcp_agent_server/asyncio`](./examples/mcp_agent_server/asyncio/)。

### MCP 服务器管理

使用 `MCPAggregator` 或 `gen_client` 统一管理多个 MCP 服务器连接，并对外暴露合并后的工具集。

```python
from mcp_agent.mcp.mcp_aggregator import MCPAggregator

async with MCPAggregator.create(server_names=["fetch", "filesystem"]) as aggregator:
    tools = await aggregator.list_tools()
```

参考文档：[连接到 MCP 服务器](https://docs.mcp-agent.com/mcp-agent-sdk/core-components/connecting-to-mcp-servers) • 示例：[`examples/basic/mcp_server_aggregator`](./examples/basic/mcp_server_aggregator/)。

## 云端部署

部署至 mcp-agent Cloud，即可获得托管的 Temporal 持久化执行引擎、安全密钥托管以及标准 HTTPS MCP 端点。

```bash
uvx mcp-agent login
uvx mcp-agent deploy my-agent
uvx mcp-agent cloud apps list
```

参考文档：[云端服务概览](https://docs.mcp-agent.com/cloud/overview) • [部署快速开始](https://docs.mcp-agent.com/cloud/deployment-quickstart) • 示例：[`examples/cloud`](./examples/cloud/)。

## 示例项目

欢迎浏览 [gallery.md](gallery.md)，查看按概念分类的可运行示例、演示视频以及社区精选项目。每个条目均附有对应的文档页面与本地运行命令。

## 常见问题 (FAQs)

### 使用 mcp-agent 的核心优势是什么？

mcp-agent 提供了一种流畅高效的方式，利用 **MCP**（Model Context Protocol）服务器暴露的能力来构建 AI 智能体。

MCP 协议本身偏底层，而本框架为您封装了连接服务器、与大语言模型交互、处理外部信号（如人工输入）以及通过持久化执行维护状态等底层机制。这使作为开发者的您能够专注于 AI 应用的核心业务逻辑。

核心优势包括：

- 🤝 **互操作性（Interoperability）**：确保任意数量 MCP 服务器暴露的任何工具都能无缝接入您的智能体。
- ⛓️ **可组合性与可定制性（Composability & Customizability）**：以可组合的方式实现了业界验证的标准工作流模式，支持自由组装复合工作流，并允许对模型提供商、日志、编排器等进行深度定制。
- 💻 **编程式控制流（Programmatic control flow）**：保持纯粹与简单——开发者只需编写普通 Python 代码，而无需陷入复杂的图（Graphs）、节点（Nodes）与边（Edges）概念。分支逻辑直接用 `if` 语句，循环直接用 `while` 循环。
- 🖐️ **人工输入与信号（Human Input & Signals）**：原生支持暂停工作流以等待外部信号（如人工审批或输入），并将其直接暴露为智能体可调用的标准工具调用。

### 使用 mcp-agent 必须依赖 MCP 客户端吗？

不需要！您可以在任何地方使用 mcp-agent，因为它会自动为您处理 `MCPClient` 的创建与管理。这意味着您可以在 Claude Desktop 等 MCP 宿主环境之外独立使用各类 MCP 服务器。

您可以通过以下三种方式架构您的 mcp-agent 应用：

#### 1. MCP-Agent 服务器（Server-of-Servers）

您可以将 mcp-agent 应用本身暴露为标准的 MCP 服务器（参见[示例](./examples/mcp_agent_server)），使各类 MCP 客户端能够通过标准的 MCP 工具 API 与复杂的 AI 工作流交互。这实际上构成了一个“服务器之上的服务器（Server-of-servers）”。

#### 2. 嵌入 MCP 客户端或宿主

您可以将 mcp-agent 直接嵌入到自定义 MCP 客户端中，用于统一编排与管理跨多个 MCP 服务器的交互。

#### 3. 独立应用（Standalone）

您可以完全独立地运行 mcp-agent 应用（即不作为任何 MCP 客户端的一部分）。[`examples`](/examples/) 目录中的所有示例均为独立应用。

### 如何部署到云端？

使用 `uvx mcp-agent login` 登录后，运行 `uvx mcp-agent deploy <app-name>` 即可。CLI 会自动打包您的项目、配置密钥，并暴露一个由持久化 Temporal 运行时驱动的标准 MCP 端点。分步截图与 CLI 输出详见[云端快速开始](https://docs.mcp-agent.com/get-started/cloud)。

### API 参考手册在哪里？

每一个类、装饰器和 CLI 命令均已在 [docs.mcp-agent.com](https://docs.mcp-agent.com) 中提供完整文档。[API 参考手册](https://docs.mcp-agent.com/reference)与 [`llms-full.txt`](https://docs.mcp-agent.com/llms-full.txt) 经过专门设计，方便大语言模型（或您本人）轻松读取全部 API 细节。

### 分享一个有趣的彩蛋

我曾考虑将这个项目命名为 _silsila_（سلسلہ），在乌尔都语中意为“一连串事件”。虽然 `mcp-agent` 这个名字更加直观务实，但项目中依然保留了一个向 _silsila_ 致敬的彩蛋。

## 参与贡献

我们非常欢迎任何规模的贡献——无论是修复 Bug、新增示例、完善文档还是提出新功能建议。请先阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)，发起 Discussion 讨论，或加入我们的 [Discord 社区](https://lmai.link/discord/mcp-agent)。

mcp-agent 的成长离不开众多开源贡献者的不懈努力，在此向大家致以诚挚的感谢！

<p align="center">
  <a href="https://github.com/lastmile-ai/mcp-agent/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=lastmile-ai/mcp-agent" alt="Contributor faces" />
  </a>
</p>

---

> **翻译说明（Translation Disclaimer）**
> 本文档由社区志愿者（[@JasonYeYuhe](https://github.com/JasonYeYuhe)）人工翻译并维护，旨在降低中文开发者的阅读门槛。最后同步日期：2026年10月26日。若译文与英文原版存在任何出入或滞后，请以 [英文原版 (README.md)](README.md) 为准。欢迎通过 PR 协助改进译文！
