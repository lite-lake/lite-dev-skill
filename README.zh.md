# lite-dev-skill

[English](README.md) | **简体中文**

`lite-dev` 是一套 Agent 为主的开发流程，以可安装的 **skill** 形式分发：一份协议、
一套模板，加一个由 profile 驱动的小工具。装上它、写一份 profile，Agent 就能把一次
改动从澄清一路做到记录在案的收尾，而不必自己发明流程。

仓库：<https://github.com/lite-lake/lite-dev-skill>

- 单仓库优先。不假设 workspace、服务网格，也不假设你的 CI。
- 零安装：仅用 Python 3.11+ 标准库（`tomllib`），无第三方依赖。
- Agent 就是运行时。skill 是入口；脚本和参考资料按需加载。

## 它是什么

一个末端由机器兜底的闭环：

```text
需求
  -> 澄清（最多 5 问，一次问完）
  -> 工作项（item.md，AC）
  -> 设计（仅在改动大或风险高时）
  -> 批次（B1..Bn，覆盖全部 AC）
  -> 逐批 implement -> verify -> commit
  -> 门禁（跑项目自己的命令，不是我们的）
  -> 发布记录（可选通道）
  -> done（AC 勾选、证据齐备）
```

有三点让它不同于普通清单：

1. **状态由工具推导，从不手写。** `flow.py` 读文件告诉你工作项到哪一步了，没有会
   漂移的状态字段。
2. **门禁就是项目自己的命令。** lite-dev 只定义阶梯（l1/l2/l3）以及何时够用，
   从不发明构建命令。
3. **绕行可见，但不阻断。** 没有工作项的提交记为发布欠账，而不是把流程变成审批警察。

## 它不是什么

- 不是任务看板、不是 spec 生成器、也不是项目管理工具。
- 不替代你的测试。它决定测试*何时*跑、*什么算*证据。
- 不是多仓库编排器。仅支持单仓库。

## 快速开始

1. **安装 skill。** 克隆仓库，然后把 `skills/lite-dev/` 放到你的 harness 能发现 skill
   的位置（例如 `.claude/skills/`、`.agents/skills/`，或用户级 skills 目录），
   或者在你的 `AGENTS.md` 里指向 `skills/lite-dev/SKILL.md`。

   ```bash
   git clone https://github.com/lite-lake/lite-dev-skill.git
   ```

2. **创建 profile。**

   ```bash
   mkdir -p docs/flow
   cp <skill>/profile.template.toml docs/flow/profile.toml
   ```

   修改 `commands`、`gate`、`mainline`、`[flow] requires`、`docs.required`。
   这是唯一含项目事实的文件。

3. **设置身份。** 每个人一份，每台机器都设一次：

   ```bash
   git config --global lite-dev.owner "你的名字"
   ```

   `new` 不猜身份：拿不到 owner 就不建条目。`LITE_DEV_OWNER` 和 `--owner` 可覆盖；
   `flow.py whoami` 显示这台机器上实际生效的身份和来源。

4. **对 Agent 说。**「在这个仓库接入 lite-dev」，或直接说「实现 X」。skill 会在
   实现、修复、设计、发布类请求上触发。

5. **随时检查。**

   ```bash
   python3 <skill>/scripts/flow.py status --mine
   python3 <skill>/scripts/flow.py check
   ```

## 仓库结构

```text
spec/invariants.md          给人看的入口，指向唯一权威文件
skills/lite-dev/            可安装的 skill，依赖全部在目录内
  SKILL.md                  入口：原则、路由、停止条件、红线
  profile.template.toml     复制到 docs/flow/profile.toml
  references/               不变量 + 按情境加载的细则
  templates/                item / design / test-report / implementation / release / retro / decision
  extensions/               随 skill 分发的扩展（go-service、security-scan、deploy-lane）
  scripts/flow.py           new / claim / whoami / status / check / design-ready /
                            gate / done / handoff / archive / unarchive / release /
                            reconcile / extensions
  scripts/flowlib/          profile、身份、产物解析、检查、文档卫生、门禁账本、
                            交接提示词、归档、命令执行、原子写入与写者锁
  scripts/tests/            单元测试 + 端到端验收
examples/minimal/           可直接跑的单仓库示例项目
```

## 哪些是确定性的，哪些不是

| 确定性（`flow.py`） | 模型 |
|---|---|
| 时间有序的 id 分配、目录脚手架 | 澄清提问、权衡取舍 |
| frontmatter / AC / 批次解析 | 设计叙述与图示 |
| 状态推导 | 批次拆分 |
| 必填字段、链接、AC↔批次↔验证 | 代码与测试 |
| 设计门禁（确认、回滚、缺口） | 故障诊断 |
| 执行 profile 命令、退出码 | 黑盒验收判断 |
| 按提交图排序的发布链 | 部署判断 |
| 从产物拼出交接提示词 | 下一步该做什么的判断 |
| 文档可达性、索引覆盖、入口文档的事实 | 文字是否属实 |
| 风险路径的设计门、本克隆的门禁新鲜度 | 改动实际有多险 |

线左边一律交给脚本，因为 Agent 自己汇报这类事总是失真；
线右边一律交给文字，因为脚本会判断错。

## 两个值得知道的设计决定

- **标题是解析契约。** 产物标题（`## AC`、`## Batches` 等）保持英文，使解析与语言
  无关。正文可以用任何语言写；`project.language` 只影响生成的文字。
- **用 TOML，不用 YAML。** `tomllib` 在标准库里，工具因此零依赖。profile 里是 shell
  命令：把它当作可信的项目配置，而不是来自不可信来源的数据。

## 发布与扩展

```bash
flow.py release --channel staging      # 只出计划：门禁、提交、欠账、记录路径
flow.py release --channel staging --record --rollback "..." --note "..."
flow.py reconcile                      # 建议性欠账报告，永不阻断
flow.py extensions                     # 每个扩展贡献了什么
```

`--record` 会自己跑门禁，之前跑过不算证据。它会拒绝脏工作树、非 `release.mainline`
分支、空的回滚说明、不是已记录 tip 后代的 source，以及没有写进 `--note` 的无工作项
提交。

扩展是声明式、只加不减的：命令、门禁步骤、必需文档、风险路径。加载器拒绝命令冲突、
未知键和与 `requires` 不兼容的版本区间。随 skill 分发的扩展可以自带脚本，并在命令里
用 `{skill}` 引用，加载器会把它展开为已安装的 skill 目录。

随附三个：`go-service`（build/vet/test 与 Go 风险路径）、`security-scan`（追踪文件里
有凭据就让门禁失败）、`deploy-lane`（校验部署 manifest）。

## 团队与多台机器

流程只依赖文件和 git：没有服务端、没有锁服务、也不发网络请求。下面这些规则让它同时
适配多人、多机与并行 Agent 会话：

- **id 按时间排序，分配不需要协调。** `{date}-{type}-{time}` 把当地当天的毫秒写进
  id，克隆可以独立分配，同一时区同一天内 id 按创建顺序排列。唯一残留的碰撞是两个
  创建者落在同一毫秒；`check` 会报重复而不合并。前缀命中两条时是错误并列出候选，
  工具从不猜。
- **归属必须显式。** `owner` 必填，来源是 `--owner`、`$LITE_DEV_OWNER` 或
  `git config lite-dev.owner`，绝不取 `user.name`。`whoami` 显示生效值和来源；
  `claim` 接管条目，`status --mine` 按人过滤。接管别人未关闭的条目需要 `--takeover`，
  `done` 会写入 `closed_by`，可选的 `[project] owners` 名单让 `check` 报出名单之外的
  拼写。
- **发布按提交图排序。** `--record` 只在主线执行；落后的克隆会被拒绝而不是记下更旧
  的 source；读坏或分叉的记录会中止发布。

`gate --work <ID>` 只校验该条目和必需文档，所以同事的半成品不会阻塞你的批次；裸
`check` 和发布仍然校验全量。`status` 显示分支、HEAD 和相对上次 fetch 的距离
（`status --json` 给脚本用），且它自己从不 fetch。写入是原子的（LF 换行、
`os.replace`），同一克隆内的写者由锁串行化，两个 Agent 会话不会交错读改写。

细节见 [collaboration.md](skills/lite-dev/references/collaboration.md)。

## 状态

当前版本已实现 `new`、`claim`、`whoami`、`status`、`check`、`design-ready`、`gate`、
`done`、`handoff`、`archive`、`unarchive`、`release`、`reconcile`、`extensions`，模板
（含 `decision.md`）、不变量文档、文档卫生检查、风险路径设计门、按克隆记录的门禁
账本、三个随附扩展，以及可运行的单仓库示例。计划中：多仓库 workspace profile。

版本与破坏性变更见 `CHANGELOG.md`（[中文](CHANGELOG.zh.md)）。

BSD 2-Clause 许可，见 `LICENSE`。
