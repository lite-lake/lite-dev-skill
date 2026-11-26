# lite-dev-skill

`lite-dev` 是一套 Agent 为主的开发流程，打包成可安装的 **skill**：协议 + 模板 +
一个由 profile 驱动的小工具。装进任何单仓库项目，写一份 profile，Agent 就能从
澄清一路做到收尾，不需要自己发明流程。

仓库：<https://github.com/lite-lake/lite-dev-skill>

- 单仓库优先，不假设你的 CI、语言或部署方式。
- 零安装：仅需 Python 3.11+ 标准库（`tomllib`），无第三方依赖。
- Agent 是运行时。`SKILL.md` 是入口，脚本和更深的内容按需加载。

## 闭环

```text
需求 -> 澄清（最多 5 问，一次问完）-> 工作项（AC）
     -> 设计（仅大改或高风险）-> 批次（B1..Bn，覆盖全部 AC）
     -> 逐批 implement -> verify -> commit
     -> 门禁（跑项目自己的命令）-> 发布记录 -> done（AC 勾选 + 证据）
```

三点与普通清单不同：

1. **状态由工具推导，人不写状态。** `flow.py status` 读文件给出状态，没有会漂移的状态字段。
2. **门禁就是项目自己的命令。** lite-dev 只定义 l1/l2/l3 阶梯和「哪层够用」，不发明构建命令。
3. **绕行可见，但不阻断。** 没有工作项的提交记为发布欠账，而不是把流程变成审批警察。

它不做的事：不是任务看板、不是 spec 生成器、v0.1 不支持多仓库。

## 快速开始

1. 克隆仓库，把 `skills/lite-dev/` 放进 harness 的 skills 目录（如 `.claude/skills/`、
   `.agents/skills/`），或在 `AGENTS.md` 里指向 `skills/lite-dev/SKILL.md`。

   ```bash
   git clone https://github.com/lite-lake/lite-dev-skill.git
   ```
2. 复制 `<skill>/profile.template.toml` 到 `docs/flow/profile.toml`，改
   `commands`、`gate`、`docs.required`。这是唯一含项目事实的文件。
3. 对 Agent 说「在这个仓库接入 lite-dev」或直接说「实现 X」。

随时检查：

```bash
python3 <skill>/scripts/flow.py status
python3 <skill>/scripts/flow.py check
```

## 目录

```text
spec/invariants.md          给人看的入口，指向唯一权威
skills/lite-dev/            可安装的 skill，所有依赖都在目录内
  SKILL.md                  入口：原则、路由、停止条件、红线
  profile.template.toml     复制到 docs/flow/profile.toml
  references/               不变量 + 按情境加载的细则
  templates/                item / design / test-report / implementation / release / retro
  extensions/               随 skill 分发的声明式扩展（go-service）
  scripts/flow.py           new / status / check / design-ready / gate / done /
                            release / reconcile / extensions
  scripts/flowlib/          profile、产物解析、检查、命令执行
  scripts/tests/            单元测试 + 端到端验收
examples/minimal/           可直接跑的单仓库示例
```

## 两个关键设计

- **标题是解析契约。** `## AC`、`## Batches` 等固定英文，正文语言自由；
  `project.language` 只影响生成的文字。
- **用 TOML 而不是 YAML。** `tomllib` 在标准库里，工具因此零依赖。profile 里是
  shell 命令，按可信的项目配置对待，不要把它当不可信数据执行。

## 发布与扩展

```bash
flow.py release --channel staging      # 只出计划：门禁、提交、欠账、记录路径
flow.py release --channel staging --record --rollback "..." --note "..."
flow.py reconcile                      # 只读对账，永远不阻断
flow.py extensions                     # 每个扩展加了什么
```

`--record` 会自己跑门禁，之前跑过不算证据。它会拒绝脏工作树、发布通道分支、
空回滚说明，以及没有写进 `--note` 的无工作项提交。

扩展是声明式、只加不减的：命令、门禁步骤、必需文档、风险路径。加载器拒绝命令冲突、
未知键和与 `requires` 不兼容的版本。

## 状态

当前版本已实现 `new`、`status`、`check`、`design-ready`、`gate`、`done`、`release`、
`reconcile`、`extensions`、模板、不变量文档和可运行示例。计划中：多仓库 profile。

版本与破坏性变更见 `CHANGELOG.md`。

BSD 2-Clause。
