# 变更日志

[English](CHANGELOG.md) | **简体中文**

## 0.3.1 — 2026-11-26

条目 id 带上当地当天的毫秒，因此按创建顺序排列。

### 破坏性变更

- 条目 id 改为 `{date}-{type}-{time}`。`{time}` 是当地当天零点起的毫秒数，用
  `23456789abcdefghjkmnpqrstuvwxyz` 编码为 6 位并前导补位。移除 `{rand}`；
  `[id] format` 必须包含 `{time}`。
- 本次发布之前的 id（5 位随机字符）不再匹配该格式。`check` 会报错；如果要继续使用
  这类项目，把目录名和 `id:` 字段改成当前的 id。
- 不变量 13 不再声称使用随机 token。时间码是标签与排序键，不是协调事实：两个创建者
  落在同一毫秒会得到同一个码，由 `check` 报重复 id。

### 新增

- `flowlib/stamp.py`：时钟读取、定宽编码，以及进程内不会重复发放同一个码的分配器。

### 变更

- `new` 只读一次时钟，日期和时间码不会跨过午夜；时间码冲突时递增到下一毫秒，而不是
  重抽随机 token，`new` 也会避开磁盘上已存在的码。
- `examples/minimal`、profile 模板和内置 `go-service` 扩展都要求 `>=0.3.1,<0.4`。

## 0.3.0 — 2026-11-26

支持多人、多机与并行 Agent。任何共享事实都不再依赖本地扫描、文件名或本机时钟。

1.0 之前：本项目尚未对外发布。不提供迁移路径，也不承诺兼容；1.0.0 才会是首个公开
版本。

### 破坏性变更

- 条目 id 改为 `{date}-{type}-{rand}`（5 位随机字符）。移除 `{seq}`、`{owner}` 与
  `[id] owner`；`[id] format` 必须包含 `{rand}`。
- `owner` 成为条目必填字段。`new` 依次从 `--owner`、`$LITE_DEV_OWNER`、
  `git config lite-dev.owner` 解析，取不到就拒绝，绝不猜。
- `gate --work` 与 `check --work` 只校验指定条目加 profile 必需文档。裸 `check` 和
  `release --record` 仍校验全量。
- `release --record` 只在 `[release] mainline` 上执行。feature 分支、通道分支、
  游离 HEAD 都会被拒绝；不是已记录 tip 后代的 source 也会被拒绝。
- 发布记录新增 `by`、`tool`、`## Artifacts`；文件名包含 source 短 sha。水位线改为
  渠道记录的祖先链 tip；读坏的记录、本克隆缺失的提交、落后的克隆、分叉的记录都报错，
  而不是被跳过。
- 配置了 channels 时 `[release] mainline` 必填。
- `[flow] requires` 为必填，固定 lite-dev 版本；安装版本不匹配即为 profile 错误。

### 新增

- `claim <ID>`、`status --mine`、`check --work`、`release --by`、可重复的
  `release --artifact`。
- `flowlib/identity.py`、`flowlib/fsio.py`（原子 LF 写入、每克隆写者锁）、
  `flowlib/errors.py`。
- `references/collaboration.md`：身份、id、认领、trunk 假设、门禁范围、发布规则、
  冲突处理、一人多机清单。
- 不变量 13：身份抗碰撞，且从不猜。
- 测试覆盖跨克隆 id、前缀歧义、条目级门禁、发布链校验（落后、分叉、断链、读坏）
  以及 LF 写入。

### 变更

- 不变量 3、4、8：状态措辞、门禁范围、记录内容与祖先链水位线。
- `reconcile --since` 必须是 HEAD 的祖先；无法排序的渠道退出 2。
- 所有平台上的写入都是原子的、使用 LF 换行；同一克隆内的两个会话会串行化读改写。

## 0.2.1 — 2026-11-26

### 新增

- `CHANGELOG.zh.md`：变更日志的中文版，与 `CHANGELOG.md` 逐节对齐。
- `README.zh.md` 重写为 `README.md` 的完整镜像（此前是精简版，缺「哪些是确定性的」
  表格等章节）。
- 两份 README 和两份 CHANGELOG 顶部都加了语言切换链接。

### 变更

- 许可从 MIT 改为 BSD 2-Clause。更新 `LICENSE`、`skills/lite-dev/SKILL.md` 的
  `license` 字段，以及 `README.md` 和 `README.zh.md` 中的许可说明。无代码或协议变更。
- `__version__` 现为 `0.2.1`。`v0.2.0` 保持已发布状态，仍为 MIT。
- 从两份 README 中删除了 `(v0.1)` 版本号，遵守不变量 9「入口文档不含版本号」。
  正文改为「不是多仓库编排器。仅支持单仓库。」

## 打包 — lite-dev-skill

- 分发仓库为 <https://github.com/lite-lake/lite-dev-skill>。
- skill 名称保持 `lite-dev`：它既是流程名，也是触发词。
- 无行为变更；工具版本仍为 0.2.0。

## 0.2.0 — 2026-11-26

### 新增

- `release`：默认只出计划，加 `--record` 才写入。只有 `check` 通过、配置的
  `release.gate_level` 通过、工作树干净、分支不是发布通道、且 `--rollback` 非空，
  才会写记录。没有工作项的提交必须写进 `--note`。
- 发布水位线：最近一条记录的 `source` 作为下一个区间的起点，`previous` 记录血缘。
  记录由 `templates/release.md` 渲染。
- `reconcile`：建议性报告（`no work item`、`missing work item`、`risky path
  without item`、`uncommitted`），支持 `--since`、`--json`、`--verbose`。
  只要能产出报告就退出 0；它永不阻断。
- 扩展加载器：声明式 `extension.toml`，先从项目解析、再退回 skill，`requires`
  版本区间为必填。合并只增不减；命令冲突、未知键、删除规则都算错误。
- 内置 `go-service` 扩展（构建/vet/测试命令、门禁步骤、风险路径）。
- `extensions` 命令，显示来源、版本区间、命令和门禁新增项。
- `flowlib/git.py`、`flowlib/reconcile.py`、`flowlib/release.py`。
- 测试覆盖版本区间、扩展合并与失败情形、对账分类、发布记录、水位线、脏工作树与
  通道分支的拒绝。

### 变更

- `gate` 与 `release` 共用一个命令执行器；任何一步失败即终止整轮。
- `check --json` 现在包含 lite-dev 版本和已解析的扩展。
- `release --record` 复用与 `gate` 相同的静态检查。

## 0.1.0 — unreleased

首个版本。目标是自洽的单仓库闭环，而不是与既有工具对齐功能。

### 新增

- `spec/invariants.md`：十二条不可妥协项，每条都写明执行方式。
- `skills/lite-dev/SKILL.md`：入口，带渐进披露的路由表。
- `references/`：澄清、一次性 vs 两阶段、角色、harness 模式、发布通道、对账、反模式。
- `templates/`：item、design、test-report、implementation、release、retro。
- `scripts/flow.py` + `flowlib/`：
  - `new`（分配 id、建目录、渲染模板）
  - `status`（推导状态、AC 进度）
  - `check`（字段、枚举、AC、链接、设计规则、必需文档）
  - `design-ready`（交接、图示、确认、批次、验证、回滚）
  - `gate`（先做静态检查，再按层级跑 profile 命令，返回退出码）
  - `done`（AC 与设计前置条件，写入 `closed:`）
- `examples/minimal`：带真实测试、可直接跑的单仓库项目。
- 单元测试覆盖 profile 加载、解析、状态推导、设计门禁、命令执行、工作项关闭。

### 已知限制

- `release` 与 `reconcile` 已在 references 中定义，但尚未实现。
- 没有扩展加载器；扩展包目前只是目录约定。
- 仅支持单仓库；没有 workspace profile。
- 身份（`owner`）是 profile 字段，不是本机约定。

### 决定

- TOML profile，仅用 Python 标准库。无依赖、无安装步骤。
- 产物标题用英文且保持稳定；正文语言自由。
- 工具从不发明命令：门禁层级映射到 profile 的 `[commands]`。
