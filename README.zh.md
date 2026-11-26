# lite-dev-skill

[English](README.md) | **简体中文**

`lite-dev` 是一套 Agent 为主的开发流程，以可安装的 **skill** 形式分发：一份协议、
一套模板，加一个由 profile 驱动的小工具。装上它、写一份 profile，Agent 就能把一次
改动从澄清一路做到记录在案的收尾，而不必自己发明流程。

仓库：<https://github.com/lite-lake/lite-dev-skill>

- 默认单仓库；多仓工作空间只差一张表。
- 零安装：仅用 Python 3.11+ 标准库（`tomllib`），无第三方依赖。
- Agent 就是运行时。skill 是入口；脚本和参考资料按需加载。

## 它是什么

一个末端由机器兜底的闭环：

```text
需求
  -> 澄清（最多 5 问，一次问完）
  -> 工作项（item.md，AC）
  -> 设计（由 profile.required_for 或 risk_paths 决定；M 默认包含）
  -> 批次（B1..Bn，有序，覆盖全部 AC）
  -> 逐批 implement -> verify（追加证据）-> commit
  -> 门禁（跑项目自己的命令，不是我们的）
  -> 发布记录（可选通道）
  -> done（AC 勾选、证据、门禁 PASS、身份）
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
- 不是构建编排器。它只运行你配置的命令，并按改动涉及的仓库收窄；它不拉取代码、
  不构建镜像、不部署。

## 快速开始

1. **安装 skill。** 克隆仓库，然后把 `skills/lite-dev/` 放到你的 harness 能发现 skill
   的位置（例如 `.claude/skills/`、`.agents/skills/`，或用户级 skills 目录），
   或者在你的 `AGENTS.md` 里指向 `skills/lite-dev/SKILL.md`。

   ```bash
   git clone https://github.com/lite-lake/lite-dev-skill.git
   ```

2. **生成项目骨架。**

   ```bash
   python3 <skill>/scripts/flow.py init
   ```

   它会写出 `docs/flow/profile.toml`（钉住当前安装的版本，并填入探测到的主线分支）、
   必需的入口文档，并在 `AGENTS.md` 里插入路由块（有标题时插在标题之后）。已存在的
   文件一律不覆盖；最后它会跑一次 `check` 并打印下一步。然后编辑 `commands`、`gate`
   和 `[design] risk_paths`：profile 是唯一含项目事实的文件。

3. **设置身份。** 每个人一份，每台机器都设一次：

   ```bash
   git config --global lite-dev.owner "你的名字"
   ```

   `new` 不猜身份：拿不到 owner 就不建条目。`LITE_DEV_OWNER` 和 `--owner` 可覆盖；
   `flow.py whoami` 显示这台机器上实际生效的身份和来源。

4. **对 Agent 说。**「在这个仓库接入 lite-dev」，或直接说「实现 X」。skill 会在
   实现、修复、设计、发布类请求上触发。需要设计时用 `flow.py design <ID>` 生成脚手架。
   每个条目收尾都需要一份累计的 `test-report.md`、一条记录在案的 full level 门禁
   PASS，以及身份。

5. **随时检查。**

   ```bash
   python3 <skill>/scripts/flow.py status --mine
   python3 <skill>/scripts/flow.py check
   ```

## 接入已有项目

已经有代码、测试和习惯的项目不必重来。闭环从下一次改动开始，接入过程是显式的：

1. **`flow.py init --adopt`。** 它保留找到的每个文件，在 `AGENTS.md` 里插入路由块，
   并把现有文档树如实报出来：漂移是 warning，缺必需文档或断链是 error。真正的冲突
   用一条 `[[exempt]]` 记录（一个检查、一个路径、一个理由、一个到期日），而不是给
   整个项目关掉检查。
2. **提交骨架之后跑 `flow.py init --baseline`。** 它把 `HEAD` 记成
   `[reconcile] baseline`；从此 `reconcile` 只报告绕开流程的改动，不再把接入前的历史
   算作欠账。
3. **第一个条目应当是收敛事实的那个。** 盘点哪些事实没有唯一归口、并给它们各建一处
   权威，是给后面所有条目付账的条目：它产出的设计模板会被后续条目照抄。

不做任何回填：不补造追溯条目，不重写历史。确实等不及条目的改动，用发布 `--note`
记录欠账，`reconcile` 会让它一直可见。

## 仓库结构

```text
spec/invariants.md          给人看的入口，指向唯一权威文件
skills/lite-dev/            可安装的 skill，依赖全部在目录内
  SKILL.md                  入口：原则、路由、停止条件、红线
  profile.template.toml     复制到 docs/flow/profile.toml
  references/               不变量 + 按情境加载的细则
  templates/                item / design / test-report / implementation / release / retro / decision
  extensions/               随 skill 分发的扩展（go-service、security-scan、deploy-lane）
  scripts/flow.py           init / new / claim / whoami / status / check / design /
                            design-ready / gate / done / drop / handoff / archive /
                            unarchive / release / reconcile / extensions
  scripts/flowlib/          profile、身份、产物解析、检查、文档卫生、门禁账本、
                            交接提示词、归档、命令执行、项目脚手架、原子写入与写者锁
  scripts/tests/            单元测试 + 端到端验收
examples/minimal/           可直接跑的单仓库示例项目
examples/workspace/         可直接跑的工作空间：一个根，两个仓库
```

## 哪些是确定性的，哪些不是

| 确定性（`flow.py`） | 模型 |
|---|---|
| 脚手架：profile、入口文档、`AGENTS.md` 路由、主线分支 | 项目实际上是什么 |
| 时间有序的 id 分配、目录脚手架 | 澄清提问、权衡取舍 |
| frontmatter / AC / 批次解析 | 设计叙述与图示 |
| 状态推导 | 批次拆分 |
| 必填字段、链接、AC↔批次↔验证 | 代码与测试 |
| 所有条目的证据完整性（每个 AC 一行命令与输出、结论） | 证据是否充分 |
| 设计门禁（确认、回滚、缺口、有序批次图） | 故障诊断 |
| 执行 profile 命令、退出码、记录在案的 full level PASS | 黑盒验收判断 |
| 按提交图排序的发布链；区分记账提交与欠账 | 部署判断 |
| 从产物拼出交接提示词 | 下一步该做什么的判断 |
| 文档可达性、索引图连通、入口文档的事实、归档索引 | 文字是否属实 |
| 决策链、豁免到期、条目停滞（git 推导） | 哪些东西该清理或重审 |
| 风险路径的设计门（扫描整段历史，每条命中标注 worktree 还是已提交） | 改动实际有多险 |
| 本克隆的门禁新鲜度、`done` 实际收口的最严级别、正在运行的版本 | 记录在案的 PASS 是否仍然有效 |
| 身份、claim/takeover、归档只读生命周期 | 谁有权改什么 |

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
flow.py release --channel staging --record --rollback "..." --confirm "..." --confirmed-by "..."
flow.py reconcile                      # 建议性欠账报告，永不阻断
flow.py extensions                     # 每个扩展贡献了什么
```

`--record` 会自己跑门禁，之前跑过不算证据。它会拒绝脏工作树、非 `release.mainline`
分支、落后于上游的克隆、空的回滚说明、不是已记录 tip 后代的 source，以及没有写进
`--note` 的无工作项提交。只新增发布记录或归档条目的提交是记账提交，不算欠账。profile
打开 `[release] confirm_risk_paths` 后，触及 `[design] risk_paths` 的发布范围还需要
`--confirm`；当批准人不是记录人时用 `--confirmed-by` 点名。记录里会留下人的原话，
而不只是回滚方案。

扩展是声明式、只加不减的：命令、门禁步骤、必需文档、风险路径。加载器拒绝命令冲突、
未知键和与 `requires` 不兼容的版本区间。随 skill 分发的扩展可以自带脚本，并在命令里
用 `{skill}` 引用，加载器会把它展开为已安装的 skill 目录。

随附三个：`go-service`（build/vet/test 与 Go 风险路径；构建输出写到临时目录）、
`security-scan`（索引里或未跟踪的非忽略文件里有凭据就让门禁失败）、`deploy-lane`
（校验部署 manifest）。

## 一个根，多个仓库

工作空间是一个容纳多个克隆、自身不是仓库的目录。它只声明三件事，其余随之工作：

```toml
[project]
root = "."                  # 显式声明；自动探测会停在 docs/（它自己是一个克隆）
docs_dir = "docs"
work_dir = "docs/work"

[workspace]
control = "docs"            # 工作项、发布记录、门禁账本都在这里

[[workspace.repo]]
path = "svc-a"
mainline = "main"

[commands]
svc_a_test = { dir = "svc-a", run = "go test ./..." }
```

- **门禁在改动发生的地方运行。** 带 `dir` 的命令属于某个仓库；门禁按改动涉及的
  仓库收窄（先看提交，再看 worktree，再看设计的 Repo 列），并说明跳过了什么、
  哪一项没能检查。`gate --repo svc-a` 可直接覆盖作用域，`status --repo svc-a` 列出该仓库
  历史提到过的条目。这正是「l1 保持便宜」
  与「l1 不降低证明力」可以同时成立的原因。
- **变更检测跨仓库。** 每条路径都带仓库前缀，所以
  `[design] risk_paths = ["svc-a/migrations/"]` 一份清单就覆盖整个工作空间。
- **发布按仓库。** `[[release.channel]]` 把频道绑定到一个仓库，记录带 `repo:`，
  链按该仓库的历史排序——规则没变，只是用在了对的图上。一起上线的频道可以组成
  `[[release.group]]`：一条命令逐仓记录、门禁只跑一次，再写一条索引记录把它们串起来。
- **文档有了记录仓清单。** `[docs] stores` 声明需求与素材目录，它们不再被要求提供
  索引；根内部的跨仓链接是正常的，绝对路径或越出根的链接是警告，用「有期限的豁免」
  登记。

不写 `[workspace]`，得到的就是 0.3.x 的单仓行为，一点不差。细节见
[references/workspace.md](skills/lite-dev/references/workspace.md)。

## 团队与多台机器

流程只依赖文件和 git：没有服务端、没有锁服务、也不发网络请求。下面这些规则让它同时
适配多人、多机与并行 Agent 会话：

- **id 按时间排序，分配不需要协调。** `{date}-{type}-{time}` 把当地当天的毫秒写进
  id，克隆可以独立分配，同一时区同一天内 id 按创建顺序排列。唯一残留的碰撞是两个
  创建者落在同一毫秒；`check` 会报重复而不合并。前缀命中两条时是错误并列出候选，
  工具从不猜。
- **归属必须显式。** `owner` 必填，来源是 `--owner`、`$LITE_DEV_OWNER` 或
  `git config lite-dev.owner`，绝不取 `user.name`。`whoami` 显示生效值和来源；
  `claim` 接管条目，`status --mine` 按人过滤。接管别人未关闭的条目需要
  `--takeover --reason "..."`；已关闭条目不能 claim，归档条目在 unarchive 前只读。
  `done` 需要身份并写入 `closed_by`，可选的 `[project] owners` 名单让 `check` 报出
  非规范拼写。
- **发布按提交图排序。** `--record` 只在主线执行；落后于上游的克隆会被拒绝；未 fetch
  的克隆本地无法识别，必须先 pull。读坏或分叉的记录会中止发布；来自陈旧克隆的坏记录
  用 revert 提交修复，绝不直接编辑记录。

`gate --work <ID>` 只校验该条目和必需文档，所以同事的半成品不会阻塞你的批次；裸
`check` 和发布仍然校验全量。`status` 显示分支、HEAD 和相对上次 fetch 的距离
（`status --json` 给脚本用），且它自己从不 fetch。写入是原子的（LF 换行、
`os.replace`），同一克隆内的写者由锁串行化，两个 Agent 会话不会交错读改写。

细节见 [collaboration.md](skills/lite-dev/references/collaboration.md)。

## 状态

当前版本已实现 `init`（含 `--adopt` 与 `--baseline`）、`new`、`claim`、`whoami`、
`status`（含 `--stale`）、`check`、`design`、`design-ready`、`gate`、`done`、
`drop`、`handoff`、`archive`、`unarchive`、`release`、`reconcile`、`extensions`，
模板（含 `decision.md`）、
不变量文档、文档卫生检查、索引图连通、决策链、带到期日的豁免台账、累计证据校验
（`done` 拒绝任何缺少通过报告、缺少记录在案的 full level PASS、或缺少身份的条目）、
有序批次图、按整段历史判定并标注 worktree/已提交来源的风险路径设计门、
`done`/`status`/`init` 打印的最严级别提示、按克隆记录的门禁账本、
发布记账与欠账分离、三个随附扩展，
按仓库区分的命令与门禁收窄、按仓库绑定的发布频道、可配置的文档记录仓，
以及两个可运行示例（单仓与工作空间）。

版本与破坏性变更见 `CHANGELOG.md`（[中文](CHANGELOG.zh.md)）。

BSD 2-Clause 许可，见 `LICENSE`。
