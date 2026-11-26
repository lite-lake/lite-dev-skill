# 变更日志

[English](CHANGELOG.md) | **简体中文**

## 0.4.1 — 2026-11-27

工作空间那一版留下了三处毛边和一处文案缺口，这一版把它们收掉，协议不变。

### 新增

- `check` 会报告本机看不到的已声明仓库：未检出，或不是 git 工作树。门禁每次运行都
  会点名它；现在 `check` 在项目校验这一步说一次。
- `status --repo <路径>` 把条目列表收窄到该仓库历史提到过的条目，并打印正在过滤哪个
  仓库。发布列车与交接就是按仓库问这个问题的。
- 批次交接（`handoff <ID> --batch Bx`）会在门禁命令里带上该批次所属仓库
  （`--repo <路径>`），实现角色不必再自己推断作用域。Repo 为 `.` 的批次保持原命令。

### 变更

- `references/workspace.md` 补上工作空间需要的权威划分：需求文档、条目、任务看板、
  发布记录。条目一旦建立，需求文档的状态字段即冻结为指针。
- `references/invariants.md` 在不变量 9 下登记这条规则，并把缺失的检查明确列为债务，
  而不是让它停留在隐含约定。
- `references/collaboration.md` 不再说「只有一条主干」：频道在各自仓库的主干上记录；
  工作空间里的 `status` 每个仓库打印一行。
- `references/workspace.md` 写明唯一剩下的发布限制：`[reconcile] baseline` 是控制仓
  里的提交，绑定到其他仓库的频道在尚无记录时用 `--since`。

### 破坏性变更

- 无。`>=0.4.0,<0.5` 仍然匹配，无需改 profile。

## 0.4.0 — 2026-11-27

一个项目根现在可以容纳多个 git 仓库。工作空间显式声明根、承载流程自身记录的仓库，
以及它可能改动的仓库；门禁、变更集、发布链、文档规则都随之工作。单仓 profile 行为
不变，一个字都不用改。

### 新增

- `[project] root` —— 显式指定项目根。根探测会向上找最近的仓库，当 `docs/` 本身是
  一个克隆时它会停错地方；`root` 相对于「包含 `docs/` 的那个目录」。
- `[workspace] control` 与 `[[workspace.repo]]` —— 控制仓承载工作项、发布记录和门禁
  账本；每个声明的仓库有自己的主干。`work_dir` 与 `release_dir` 必须位于控制仓内，
  嵌套仓库会被拒绝。
- 按仓库区分的命令：`[commands]` 的值可以是表
  （`svc_a_test = { dir = "svc-a", run = "go test ./..." }`）。只有该仓库在作用域内
  时门禁才跑这一步；没有 `dir` 的步骤始终运行。
- `gate --repo <路径>`（可重复，`.` 表示控制仓）覆盖作用域。`status` 为每个仓库打印
  一行：分支、HEAD、距上次拉取的差距、脏文件数；`status --json` 带 `repos`。
- 变更检测遍历每个声明的仓库，并给每条路径加上仓库前缀，因此一份风险清单覆盖整个
  工作空间。缺失或读不到的仓库会被报出来，而不是被当成「没有改动」。
- `[[release.channel]]` 把频道绑定到仓库；记录带 `repo:`，链按该仓库的历史排序。
  没有该字段的老记录按控制仓读取。
- `[docs] stores` 声明记录仓与素材库（支持 glob），它们不是文档树；
  `[docs] surfaces` 增加 `docs_dir` 之外的文档根。
- 两个新的文档检查：绝对路径链接（`absolute`）与越出项目根的链接（`escape`）。
  两者都是警告，配「有期限的豁免」，不是开关。指向已声明仓库内部的链接属正常。
- `[project] owner_file` —— 根不是仓库时，用按机器维护的身份文件。`git config
  lite-dev.owner` 先读控制仓，再读根。
- `item.md` 新增可选的 `prd:` 与 `board:` 指针；`check` 报告指向不存在的文件，
  `handoff` 会打印它们。
- `examples/workspace` —— 一个可运行的双仓库工作空间示例，验收测试跑完整流程，
  含按仓库收窄的门禁与一次记录发布。

### 变更

- 根解析顺序：`[project] root` > 最近的仓库 > 约定的 `docs/flow` 位置。`init` 会复用
  已存在 profile 的根，不再在子目录里另起一套流程。
- `init` 写穿符号链接指向的目标，而不是替换链接本身；目标越出项目根会被拒绝；
  写入不在任何 git 工作树内时会明确提示。
- 路径前缀按目录匹配：`svc-a` 不再覆盖 `svc-a-tools/`。
- `commands.execute` 返回它实际使用的计划，门禁报告跳过了什么、没能检查什么。
  仓库缺失不再让门禁崩溃，也绝不会被静默跳过。
- `changed_paths` 不再吞掉 git 错误：降级会被报出来。
- `profile.template.toml` 要求 `>=0.4.0,<0.5`；随附扩展要求同一范围。

### 破坏性变更

- 声明了 `[workspace]` 的 profile 在 0.3.x 上无法加载（未知键）。降级需要同时回退
  profile。没有新表的 profile 加载与行为完全不变；`examples/minimal` 就是这条保证
  的守门人。
- 配置了频道时 `[release] mainline` 仍然必填，并作为每个 `[[release.channel]]` 的
  默认值。

## 0.3.9 — 2026-11-27

风险路径与回退路径现在按整段历史判定，而不是按一个窗口；每一条命中都会注明它来自
worktree 还是来自该条目自己的提交；`done` 也会说出它究竟在哪一级收口。

### 新增

- `gate --work` 为每条风险路径、回退路径命中注明来源：`db/schema.sql (worktree)`、
  `deps.txt (committed)`，或 `(worktree + committed)`。worktree 里的文件仍然参与
  判定——未提交的改动也是真实工作——但一个与本次改动无关的脏文件现在会以「worktree」
  的身份出现，而不是默默决定判定结果。
- `status` 打印正在运行的 lite-dev 版本（`status --json` 里也带 `version`），
  于是一个还在跑旧安装的克隆是看得见的。
- profile 的最严级别不是 l3 时，`done`、`status`、`init` 给一条警告：
  `the strictest gate is l1; done will close on l1`。它点出当前级别和该改的 profile，
  但拒绝条件一条都没变。

### 变更

- 风险路径与回退路径的判定扫描整段历史
  （`git log --fixed-strings --grep=<条目 id>`，`flowlib/git.commits_matching`），
  不再只看最近 200 个提交。跨天的条目不会丢掉早期提交，所以风险路径不会因为提交
  滑出窗口而静默通过门禁。
- `SKILL.md` §7 写明：l3 必须能在本地跑；只在 CI 存在的 l3 要包成一个会等待该次 CI
  的本地命令。
- `profile.template.toml` 要求 `>=0.3.9,<0.4`。

### 破坏性变更

- 无。钉在 `>=0.3.8,<0.4` 的 profile 仍可加载；风险与回退警告多了来源标注，属于
  信息变化，不是规则变化。

## 0.3.8 — 2026-11-27

接入现在由工具完成，而不是靠人照 README 抄：`init` 既能给新项目也能给已有项目搭骨架，
`reconcile` 在没有发布记录时也能从基线算起，而关掉的检查、以及开着却什么也没检查的
检查，每次运行都会自己说出来。

### 新增

- `flow.py init [--adopt] [--baseline]`：写出缺失的 `docs/flow/profile.toml`
  （钉住当前安装的版本，并填入探测到的主线分支）、必需的入口文档，并在
  `AGENTS.md` 里插入路由块（有标题时插在标题之后）。已存在的文件绝不覆盖，路由块
  不会重复插入；命令最后跑一次 `check` 并打印下一步。没有 git 也能用；`--adopt`
  会打印已有代码与文档的项目该走的接入阶梯。
- `[reconcile] baseline`：还没有发布记录时，`reconcile` 检查 `baseline..HEAD`，
  并把这次运行标为 `channel: baseline`；`--since` 可以对单次运行做同样的事。
  `init --baseline` 在干净工作树上写入它。两者都没有时，`reconcile` exit 2 并点名
  两种修法，而不是把整段历史当成报告。
- `check` 每次运行都报告 `[docs] check_links = false` 和 `zero_fact = false`；
  `zero_fact = true` 但 `[docs] required` 里没有入口文档时，报告该检查「空转」：
  开着却什么也不检查，和关掉它是同一种失败，只是多了几步。

### 变更

- 只改动 profile 的提交算记账，不算欠账：接入流程本来就要改 profile，而这种提交无法
  带工作项。风险路径在归类之前就已报告，所以碰到风险路径的 profile 改动仍会被点名。
- 缺少 profile 的错误现在会指出 `flow.py init`，而不只是 `--profile`。
- `profile.template.toml` 要求 `>=0.3.8,<0.4`。

### 破坏性变更

- 无。钉在 `>=0.3.7,<0.4` 的 profile 仍可加载。没有通道也没有基线时 `reconcile`
  仍然 exit 2，只是信息里给出了修法。

## 0.3.7 — 2026-11-26

协议现在和工具一致：M 是「单会话但有设计」，每个条目收尾都要证据和记录在案的门禁，
批次构成有序图，流程不再把自己的发布/归档提交当成欠账。

### 新增

- `flow.py design <ID>` 从模板生成 `design.md`；`flow.py drop <ID> [--reason]`
  进入 `dropped` 状态，不再需要手写 frontmatter。
- `done --owner`、`claim --reason`、`release --confirmed-by` 让归属和授权显式。
  `claim --takeover` 现在必须有理由，并记录 `takeover_by`/`takeover_reason`。
- `test-report.md` 改为累计：解析器读取每个 `## Evidence` 块，后一批追加而不是覆盖
  前一批证据。
- 校验批次图：`B1..Bn` 有序无缺口，依赖只能指向更早批次，拒绝环和自依赖。
  `handoff` 把 blocked 批次标为阻塞（不再当成 pending），拒绝派发已 done 的批次，
  不会把 draft 设计说成已确认。
- `status` 在需要设计时显示 `required`；ready 设计失效时显示 `ready!` 并给出警告。
- 发布记账与欠账分离；归档 item id 仍算已知；`## Work items` 把未知 id 标为
  `(missing)`；提交挂了 item id 的 risk path 仍会被报告。`release --record` 拒绝
  落后于上游的克隆，以及起点晚于已记录 tip 的 `--since`。
- `check` 校验归档索引，发布记录不再被要求链接进索引，重复 id 只报一次。决策指针
  接受 `none`；随附模板能通过自己的检查。
- `extensions` 打印必需文档和 reconcile 风险路径。`security-scan` 扫描索引加未跟踪
  且未忽略的文件；`go-service` 把构建输出写到临时目录。
- 导入前检查 Python 3.11+，给出可行动的错误，而不是 `tomllib` 的原始 traceback。

### 变更

- `done` 现在对**所有**条目要求 `test-report.md`、每个 AC 一行证据、该条目在最高
  门禁级别的 PASS 记录，以及身份，不再只针对设计项。
- 归档条目只读：`done`、`claim`、`drop`、`design-ready` 在 `unarchive` 前拒绝；
  `claim` 拒绝已关闭条目。
- `archive --force` 必须有 `--reason`。`[gate]` 拒绝 `l4` 这类未知级别，不再静默丢弃。
- `status` 在条目进入 ready/done 前不再提示缺少 full level PASS；更便宜的门禁仍会提示。
- 证据单元格里的 `<skill>`、`<nil>`、`<br>` 是证据，不是占位符。翻译设计标题会得到
  明确错误，指出必须保留的英文标题。
- `profile.template.toml` 要求 `>=0.3.7,<0.4`，占位测试命令在配置前会失败。

### 破坏性变更

- 升级 skill 的项目必须同步升级 profile：`done`、`claim`、归档条目命令、
  `archive --force` 和更严格的 `[gate]` 校验都是新的拒绝。
- `go-service` 的 `go_build` 改为写临时目录；`security-scan` 也扫描未跟踪文件。
  依赖旧范围的项目应在 l3 重跑两者。
- M 明确为「单会话但仍需设计」（当 `[design] required_for` 含 `M`）；minimal 示例
  已改用该默认值。

## 0.3.6 — 2026-11-26

证据、可达性和「有边界的沉默」变成检查：`done` 拒绝没有通过测试报告的设计项，
`check` 沿着索引图与决策链走，例外变成一条带理由和到期日的记录，而不是永久开关。

### 新增

- 校验 `test-report.md`：每个 AC 一行证据，含命令与输出，无占位符，`Verdict: PASS`。
  `done` 拒绝设计项的报告缺失、未通过或不完整；条目还开着时，`check` 把同样的
  问题报成 warning，不阻断迭代。
- profile 新增 `[[exempt]]`：`check`、`path`、`reason`、`until`。过期豁免是 error
  且不再静默；没有压住任何问题的豁免报为未使用；缺字段是 profile error。证据不可豁免。
- `check` 沿文档图检查：`docs_dir/README.md` 是根，每个目录索引必须从它可达，
  含 markdown 的目录必须有 `README.md`。条目与发布目录作为记录仓排除在外。
- 入口文档除版本、端口、日期外，也不得写计数（`3 services`、`2 个应用`）。
- 校验决策记录：状态枚举、`Superseded by:` 目标同目录存在、被点名者状态一致、
  id 唯一、不成环。
- `status --stale [--days N]`：列出超过 N 天没人碰的开启条目，日期由 git 推导
  （未提交的条目用 `created`）。只报告，exit 0；`--json` 带同样的行。
- `[release] confirm_risk_paths`：发布范围触及 `[design] risk_paths` 时，
  `--record` 需要 `--confirm "<人说的话>"`，记录多出 `## Authorization` 段，
  写明谁批准。
- 参考文档：角色边界（实现者与验证者不得提交、提交者不得改代码、子代理空返回
  重试一次），以及两条反模式（上游成功不是证据；轮询而不是固定 sleep）。
- `references/invariants.md` 把 `human` 与 `partly` 记为欠账，必须给出机械化候选。

### 变更

- `done` 会拒绝它以前接受的东西：设计项没有 `test-report.md`、`Verdict` 不是 PASS、
  或某个 AC 没有证据行。这正是 invariant 5 写明的规则，现在工具执行了自己那一半。
- `check` 会失败在它以前通过的地方：决策链断裂、豁免过期、豁免条目非法。
  升级后跑一次 `check`，报错会点名文件与修法。
- `release --record` 现在给每条新记录写 `## Authorization` 段（无需确认时为 `None`）。
  旧记录仍然有效。
- `profile.template.toml` 要求 `>=0.3.6,<0.4`。

### 破坏性变更

- `[[exempt]]` 与 `[release] confirm_risk_paths` 对旧版加载器是未知键：升级了
  profile 的项目必须在同一次变更里升级 skill。既有 `[flow] requires` 范围
  （如 `>=0.3.5,<0.4`）仍然接受 0.3.6，未改动的 profile 可以照常工作。

## 0.3.5 — 2026-11-26

那些「写进规格但一直靠人」的部分变成了检查：交接提示词由产物拼出而不是重打，`check`
开始读它以前信任的文档，风险路径没有设计会变得可见，过期的全量门禁会开口说话。
另外两个可选扩展覆盖凭据与部署 manifest。

### 新增

- `handoff <ID> [--batch <Bx>]`：从产物拼出冷启动提示词——工作项与设计路径、设计里
  的交接摘要原文、`## Implementation` 里的批次进度、下一个批次、门禁命令。`--batch`
  输出单个批次的 implement 派发。指令文字跟随 `project.language`，数据从不改写。
- `archive <ID> [--reason …]` 与 `unarchive <ID>`：已关闭条目移到
  `<work_dir>/_archive/<YYYY-MM>/`，并在该目录的 `README.md` 追加一行。不删除任何
  东西；归档后的 id 仍可解析，但不算在工作集里、不出现在 `status` 的列表里。
- `check` 现在校验文档，而不只是产物：
  - `docs_dir` 下的相对链接必须解析（跳过围栏代码块、行内代码与模板占位）；
  - 索引目录里的每个 markdown 文件都被该目录的 `README.md` 链接；
  - 条节目录里存在的产物文件在 `item.md` 里被提到；
  - 发布记录里不出现重复的 `##` 标题；
  - 活跃文档不直接链接 `_archive/`；
  - 入口文档（`README`、`AGENTS`）不含版本、端口、日期；
  - 配置了 `[docs] decisions` 时，目录存在且有索引。
- `[design] risk_paths`、`risk_exempt`、`risk_gate`：`gate --work` 会报告（`"block"`
  时直接拒绝）触及风险路径但没有可用设计的改动。豁免清单正是让「写风险路径的文档」
  不触发它的东西。
- `[gate] fallback_paths`：改动列出路径（锁文件、schema 运行脚本、工具链钉版）会让
  便宜的门禁失效，工具会提示去跑最严格的一级。
- `[gate] fresh_days` 与 `<git-dir>/lite-dev/` 下的按克隆门禁账本：`status` 和更便宜
  的一级会提示最严格一级的上次 PASS 已过期。仅提示，且账本永远不是工作树文件。
- 扩展命令可包含 `{skill}`，加载器把它展开为已安装的 skill 目录（shell 引用），
  随附扩展因此可以自带脚本而不写死机器路径。
- 随附 `security-scan`：追踪文件里有凭据、敏感文件名或带凭据的 URL 就让门禁失败，
  可用路径前缀白名单豁免。
- 随附 `deploy-lane`：校验部署 manifest——必填字段、已回填、RFC3339 时间、commit
  sha、不可变标签与 `sha256:` digest，以及永不为空的回滚目标。
- `templates/decision.md` 与 `[docs] decisions`，给比工作项活得更久的决策。
- `references/docs-hygiene.md`。

### 变更

- `check` 现在会在以前通过的地方失败：断链、发布记录里重复的标题、缺失的决策索引
  都是错误。升级后先跑一次 `check`，警告会指出文件和改法。
- `status` 增加门禁新鲜度一行、归档计数，`--json` 增加 `gate`。文本输出的既有使用者
  不受影响；严格解析文本的脚本应改读新字段。
- `gate` 每次运行写入本克隆账本，并在执行命令前打印 fallback 与风险路径提示。
- `done` 未变，但 `find_item` 现在也能解析归档 id；工作集与归档之间的重复仍由
  `check` 报告。
- profile 模板把 `[flow] requires` 钉到 `">=0.3.5,<0.4"`。钉 `>=0.3.2,<0.4` 的项目
  无需改动即可拿到以上全部；新键在旧安装上不可用。
- 扩展模型**没有**超出 `{skill}` 继续加键。部署记录由发布记录加文档检查覆盖，所以
  `[templates]`、`[artifacts]` 留到真有消费者需要时再加。

### 修复

- 改动路径改用 `git status --porcelain -uall`，风险门禁看到的是 `db/schema.sql`
  而不是折叠后的 `db/`，豁免也能按文件匹配。

## 0.3.4 — 2026-11-26

多人协作与多机开发：身份漂移变得可见，误接管会被拒绝，关闭条目时记录是谁关的。

### 新增

- `whoami`：打印解析到的身份、来源（`--owner`、`$LITE_DEV_OWNER`、
  `git config lite-dev.owner`）和项目。
- `status --json`：给脚本和看板用的检查点、条目与计数。文本输出新增分支、HEAD，以及
  相对远端跟踪引用的 behind/ahead；它仍然从不 fetch。
- `check` 对「只差大小写或空格」的两个 owner 给出警告；配置了 `[project] owners`
  名单时，名单之外的 owner 也会警告。
- 条目目录出现非 ASCII 字符时，`check` 提示设置 `git config core.quotepath false`。
- `done` 把 `closed_by` 写进 `item.md`，关闭者不是 owner 时给出警告。该字段可选，
  已有条目仍然有效。

### 变更

- `claim <ID>` 现在拒绝对别人的未关闭条目直接接管并以退出码 2 结束，加 `--takeover`
  才改归属。这是行为变更，按补丁版本发布：钉住 `>=0.3.2,<0.4` 的项目会直接拿到它，
  不需要改版本区间。无人拥有或已关闭的条目仍按原样接管。
- `[flow] requires` 保持 `>=0.3.2,<0.4`，没有项目需要改动。
- 文档收窄了关于 id 的说法：id 只在一个本地时区、同一天内按创建顺序排列，不是全局
  有序。`collaboration.md` 补充了跨时区与时钟回拨、接管、成员名单，以及两个克隆记录
  同一个 source 时发布记录文件名相撞的情况。
- 测试覆盖了此前只有规格、没有验证的路径：磁盘上已有同码时的 id 递增、重复 id 报告、
  第二个进程争抢每克隆写者锁、保持 LF 的原子写入。

### 修复

- 测试夹具解析临时目录，因此在 `/var` 是 `/private/var` 软链的 macOS 上也能通过。
  CI 跑在 Linux 上，此前一直没暴露。

## 0.3.3 — 2026-11-26

目录 slug 跟随标题本身的文字，不再对所有语言套同一个宽度上限。

### 变更

- 中文标题在目录名里保留汉字，上限 30 字符；英文标题保持连字符拼接和 32 字符上限。
  判断依据是标题而不是 `[project] language`：英文项目里的中文标题会保留中文 slug，
  而不是被清成空。
- 中文 slug 超过 20 字符时 `check` 给出警告。这是警告不是错误，硬上限仍是 30。
- `[flow] requires` 保持 `>=0.3.2,<0.4`：slug 只是展示，不改变门禁接受什么。

## 0.3.2 — 2026-11-26

工作条目按月份归档，长期项目不会把上千个目录堆在一个地方。

### 破坏性变更

- 条目路径改为 `<work_dir>/<YYYY-MM>/<id>-<slug>/`。月份来自条目的 `created`
  日期，由 `new` 写入一次；`check` 会报告归档到其他月份的条目。
- `<work_dir>` 下不是 `YYYY-MM` 的目录是错误，不会被跳过。0.3.2 之前的扁平条目用
  `git mv <work_dir>/<id>-<slug> <work_dir>/<YYYY-MM>/` 迁移。
- 模板、`examples/minimal` 和内置 `go-service` 扩展的 `[flow] requires` 改为
  `>=0.3.2,<0.4`：0.3.1 会去旧布局里找条目，结果一个都找不到。

### 变更

- `new` 创建月份目录并把条目放进去。
- `new` 的防重扫描只读目标月份，不再遍历整个项目的条目；id 里带着 `created`
  日期，所以候选不可能与归档在其他月份的条目相撞。
- `check` 对月份目录里没有 `item.md` 的杂项目录给出警告。

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
