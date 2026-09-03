# 维护者指南

本文件保存不应占用 SkillHub 用户概述的开发信息。教学行为以 `SKILL.md` 及其他 `references/` 协议为准。

## Demo 与校验

核心 Vault 与测试脚本要求 Python 3.10 或更高版本，并只使用 Python 标准库。发布流程图还需要 Node.js/npm、`@mermaid-js/mermaid-cli@11.12.0` 与 Pillow；这些依赖只用于生成带水印的审阅图，不进入学习运行时。

自 v0.1.3 起所有个人 Vault CLI（包括 validate）先经过三选一门。下例仅针对维护者明确选择的**合成 Demo**，不是为真实用户伪造授权；真实教学必须使用用户的实际消息引用与精确根目录。含写操作的示例应在独立的测试副本中运行，不把当前 Demo 或用户原库当作试验场。输入 JSON 与输出文件也应在被确认的数据根目录内。

```powershell
py -3 -B -X utf8 scripts\vault_tool.py learning-entry
$demoRoot = (Resolve-Path -LiteralPath 'demo-vault').Path
$demoRead = @('--data-mode', 'use_existing', '--confirmation-ref', 'synthetic-fixture-review', '--data-root', $demoRoot)
$demoWrite = $demoRead + @('--write-confirmation-ref', 'synthetic-fixture-mutation')
py -3 -B -X utf8 scripts\vault_tool.py validate --vault $demoRoot @demoRead
py -3 -B -X utf8 scripts\vault_tool.py resolve-teaching --vault $demoRoot --dry-run @demoRead
py -3 -B -X utf8 scripts\vault_tool.py prepare-teaching --vault $demoRoot @demoRead
py -3 -B -X utf8 scripts\vault_tool.py inspect-cone --vault $demoRoot @demoRead
py -3 -B -X utf8 scripts\vault_tool.py issue-route --vault $demoRoot --record <root内route-input.json> @demoWrite
py -3 -B -X utf8 scripts\vault_tool.py issue-teaching --vault $demoRoot --content <root内delivery-content.json> @demoWrite
py -3 -B -X utf8 scripts\vault_tool.py append-evidence --vault $demoRoot --record <root内evidence-input.json> @demoWrite
py -3 -B -X utf8 scripts\vault_tool.py open-verification --vault $demoRoot --process-evidence-id <committed-id> @demoRead
py -3 -B -X utf8 scripts\vault_tool.py schedule-retention --vault $demoRoot --record <root内retention-schedule.json> @demoWrite
py -3 -B -X utf8 scripts\vault_tool.py open-delayed-verification --vault $demoRoot --state-id <state-id> @demoWrite
py -3 -B -X utf8 scripts\self_test.py
py -3 -B -X utf8 -m unittest discover -s scripts -p "test_*.py"
py -3 -B -X utf8 scripts\render_flowchart.py --input review-assets\understanding-cost-flow-v0.1.4.mmd --output review-assets\understanding-cost-flow-v0.1.4.png --config review-assets\puppeteer-config.json --scale 3
py -3 -B -X utf8 scripts\check_release.py --root .
```

macOS / Linux 使用 `python3`。预期 Vault 校验为 `status: ok`、`error_count: 0`、`warning_count: 0`，回归测试为 `status: ok`。

流程图命令中的 `puppeteer-config.json` 是 Windows 默认 Chrome 安装位置的示例，仅用于维护者渲染图片。其他系统可省略 `--config` 使用 Mermaid CLI 自带的浏览器配置，或提供与本机浏览器位置相符的配置；学习运行时不依赖这个 Windows 路径。

## v0.1.4 概念交接与正文检查

- `prepare-teaching` 从当前图谱生成 `concept_inventory`，包含本步名称/别名；和已验证锚点、必需术语一起约束讲解。不是增加全图教学，也不改变 Focus 公式或路径算法。
- 新 `issue-teaching` 在写入前检查实际白名单正文和定义依赖，不能用空 `introduced_terms` 绕过登记概念。草稿新发现的词直接补 `term_grounding`；必需术语仍按原名保留，新增定义只影响投影，不改历史教学决策。
- `scripts/teaching_review.py` 是同一个纯函数检查的独立 stdin/stdout 入口，用于只读/无数据会话。输入来自本轮授权资料和证据，不用初始化 Vault；不是持久化签发、未见题防泄漏或掌握认证。
- `test_meaning_guard.py` 覆盖占位/循环自称及正常短定义；`test_teaching_review.py` 覆盖正文漏项、定义中的隐藏依赖、别名、歧义、词边界、生产拒绝零写入、只读命令和内部字段隔离。程序通过仍须 Agent 审未登记概念与实质含义，并根据真实作答检查理解。
- 合成试跑可在 PowerShell 执行下式。它只读取随包示例；真实临时教学应把当轮 JSON 直接经 stdin 传入，不把用户资料写到模板或旁路文件里。输出 `structural_pass` 不等于“用户已经懂了”。

```powershell
Get-Content -LiteralPath templates\teaching-review-session.json -Raw | py -3 -B -X utf8 scripts\teaching_review.py
```

旧 seed/历史 evidence/teaching_delivery 保留，不用改写历史内容来满足新签发检查。新概念的教学顺序、Agent 语义复核与三种事实的区分，见[文字协议](text-learning.md)；本次审阅入口见 [REVIEW-0.1.4](../review-assets/REVIEW-0.1.4.md)。

## v0.1.3 入口变更与测试范围

- `learning-entry` 无参数只给三选一；`no_personal_data` + 真实 `confirmation_ref` 只给当轮前提确认动作，不创建或打开 Vault。没有显式选择时不预选第三项。
- `create_boundary / use_existing` 必须确认精确绝对 `data_root`；个人 CLI 的 `--vault` 必须精确匹配；拒绝相对路径、其他根目录以及可跳出范围的链接路径。授权不随文件位置存在而产生。
- 既有库默认只读；writer 另需 `write_confirmation_ref`；不能用它对既有库 `init`。可用的只读调用不会更新数据库或导出画像，但部分旧函数仍使用系统临时目录中的外置事务锁；这不是全主机零写入保证。未选择和无个人数据分支在进锁之前拦截。
- `--record / --content / --output` 必须位于已确认根目录内；不能只检查 Vault 路径，却让其他输入或输出越权。
- 旧 `recover-route` 的父目录扫描不再可由学习 CLI 调用，改为请求精确位置。内部函数保留供合成测试/维护，不构成学习授权。
- 创建边界、使用既有数据库、无个人数据学习的行为样例见 [入口演示](../templates/learning-entry-demo.md)。运行 `test_learning_entry.py` 验证入口的拒绝与权限边界；行为试跑另行验证 Agent 是否真的先提问、等待与最小诊断，不能用字符串测试代替教学效果。
- `demo-vault` 和合成 seed 的历史版本保留 0.1.2；本次不更改历史作答、账本或证据以伪造真人数据模式选择。版本号 0.1.3 只属于新 Skill 发布。
- CLI 新增参数是调用兼容性变化；旧脚本缺参数将被入口门拦截，必须补真实选择。确认引用由 Agent 提供，不是用户同意的外部签名；入口不控制所有宿主工具，也不能自动适配任意数据库。

## v0.1.2 审阅与兼容边界

本版在独立开发副本内维护，不自动同步原仓库或线上包。自带 `demo-vault` 使用 v0.1.2 合成 seed 重建，补齐可直接作答的诊断材料；这不是重建用户学习历史。`seed-demo` 新建的合成图谱显式声明审核过的 prerequisite coverage。旧 v0.1.1 记录仍通过固定版本 seed 的精确前缀校验，不手改历史证据或哈希来凑通过。

可信合成 seed 只允许内置版本白名单：manifest 缺少 `seed_version` 时按旧 v0.1.1 校验，显式 `0.1.2` 按新版校验；未知版本拒绝。原始 v0.1.1 seed 保存在 `assets/demo-seed-v0.1.1.json`，新建 demo 使用 `assets/demo-seed.json`。这只提供合成 seed 前缀的外部对照，不能外推为本地追加事件的外部真实性证明，也不允许从 manifest 指定任意文件加载信任源。

旧 Vault 的绑定材料不随 seed 更新被替换；遇到旧材料只有说明而没有题目，应停止发送该不完整任务，并按正常资源准备与路线签发流程创建完整的新材料。不得修改旧签发快照、题面或证据来冒充兼容。

- 图谱不全与用户未知分开：`prerequisite_coverage` 控制建模门，`required_contrast_ids` 控制必要辨析，不冒充先修。
- 核心一到核心二使用 `prepare-teaching`，返回同一已落地决策的简报；路由动作和过程动作分别读取。生成器不要打开原始验证资源。
- 新教学内容使用[模板](../templates/teaching-content.json)。把当前简报的 `route_binding_id / decision_fingerprint / brief_fingerprint` 原样复制到 `teaching_basis`，再声明锚点与能力。新证据或路线变化使旧草稿失效；重新准备并审阅内容，不能只替换指纹强行重放旧内容。
- 旧 teaching_delivery 无需迁移；新 `issue-teaching` 强制上述输入，旧调用者须补齐字段。该补丁增加输入校验，不能称为所有旧调用代码无需修改。
- `source_revision` 用于使当前及附近同范围 state/evidence 变化失效旧简报，不是外部签名。字段声明和字面术语门不能自动证明自然语言的全部依赖，也不能检测所有语义改写泄漏。
- 提前主动复习必须通过新学习任务的独立验证；原排期未到期、未开题时才追加新排期，保持旧记录。
- 只引入同次请求的解析复用，不引入跨请求缓存、SQLite 或紧凑证据迁移。新请求和写后重建都重新读盘。

可选性能复测：`py -3 -B -X utf8 scripts/test_snapshot_regression.py --benchmark`。它比较同次快照复用与消费时独立重读，逐项核对结果相等；测量的是本机耗时/解析次数，不是模型 Token，不能外推“几百文件就是容量上限”。

主流程双边框在[详细流程](../review-assets/understanding-cost-detail-v0.1.4.mmd)与 workflow 对应章节展开。实现、两个图层与文字协议同时维护。

生产锁默认最多等待 10 秒。只有故障注入或运维诊断才可临时设置 `UNDERSTANDING_COST_LOCK_TIMEOUT_SECONDS=0..60`；超时必须返回错误且 Vault 零变化，不能以关闭互斥作为恢复方式。

`append-evidence` 的四阶段完整输入模板位于 [templates/append-evidence](../templates/append-evidence/README.md)；路线与保持模板位于 [templates/route-retention](../templates/route-retention/README.md)。teaching_process 的绑定优先从 `issue-teaching` 返回的内部 `process_binding` 复制；retention 的 `teaching_item_id` 必须来自 `open-delayed-verification` 已持久化的 open receipt。两类内部对象都不能进入用户投影。

再使用当前 Agent 环境中的 `skill-creator/scripts/quick_validate.py` 校验目录结构。SkillHub 发布包另需在暂存副本的 `SKILL.md` frontmatter 中加入平台要求的 `slug`、`version`、`displayName` 和 `summary`；不要把这些平台字段写回要求严格 frontmatter 的 Codex 源目录。

## 流程图与协议同步

[文字协议](workflow.md) 与 [v0.1.4 流程图源文件](../review-assets/understanding-cost-flow-v0.1.4.mmd) 是同一执行合同的文字版和图形版；[带 ELD 水印的审阅 PNG](../review-assets/understanding-cost-flow-v0.1.4.png) 必须由 `scripts/render_flowchart.py` 生成并嵌入 [SKILL.md](../SKILL.md)。不存在“实现优先”或“图只供参考”的关系。修改任一方时必须在同一变更中同步另一方，并运行以下一致性检查；任一状态、门、回路、回写语义、版本号或水印不一致时，该版本不得交付：

- 每个计算或保存字段都有明确消费者；无消费者分支不得进入提交；
- 用户未选择数据模式时停止；三模式路径与其读写范围一致，只读/无个人数据分支不得流入 Vault writer；
- 两种教学执行分支在实际输出前都有正文概念检查和 Agent 语义复核；未登记词与含义充分性不冒充程序已验证，新模型先解释意义并等待回答，再按需进入公式；
- 候选顺序固定为硬资格 → 路线层级 → 动作绑定 → 成本 Pareto → 用户明确成本优先维度（Demo 词典序）→ Focus；
- Focus 不包含成本，只能排序剩余 active 候选；
- residual Focus 使用 `uc-focus-snapshot/0.4`，必须精确匹配当前 `route_id + route_version + route-chain-head time_scope + decision_id batch`，并拒绝未来 `calculated_at`；
- 选中步骤后通过 `issue-route` 追加可重算验证的 route issuance hash chain，task/context/resource 快照不能由 evidence 自证；同时声明 `route_trust_level`，`trusted_seed_prefix_local_extension` 只保护 seed 前缀，本地后缀不得冒充外部防伪；
- `issue-route.user_cost_priority` 必须是 `null` 或 canonical 成本维度无重复数组；非法/矛盾的显式优先级，或显式优先级被 unresolved 阻塞时零写入拒签；`priority=null` 的 unresolved 情况只允许保留来源后受限 `route_default`，且不得消费 Focus。发行事件显式冻结 `baseline_evidence_id`：learning 为 `null`，retention 与 schedule baseline 精确相等；
- production 为每个 `concept + resource` 建立候选；只有资源完整六维 `cost_vector` 可进入已解决 Pareto。缺失时可保留带来源标签的 intervention+duration fallback estimate，但成本仍为 unresolved，显式 priority 必须拒签。发行事件冻结全部 candidate cost/缺失状态、resource fingerprint、来源和选中项，证明优先级确实改变了哪个实际资源；
- 画像只消费 state `supported_by` canonical 窗口；同一 `route binding + phase + verification task` 只允许一条 canonical evidence，重试必须签发新的 task 或 route/version，换文件或 evidence/item ID 不得增加独立样本；teaching_process 的真实重试允许追加但必须有不同 observed_at，同题同时间换 ID 是 replay；
- teaching_process 使用独立的 phase-aware 消费者窄表，两侧映射必须严格相等；它不得绑定 contract/retention/方法效果成本消费者；
- 画像选出的 activity/carrier 必须唯一解析并持久化到真实支持它的已签发 resource；同一 resolution 还要持久化从 process evidence 派生的反馈、下一动作与实测成本。实测高于路线估计时，必须在真实兼容资源中改变为最低 duration 的文字修复活动；Cone、教学投影与恢复只读该结果；
- 初始教学生成器只接收 verification content guard，用户完成教学过程前不能读取或投影原始验证题与保护答案；
- 教学过程证据必须同时绑定它实际收到的 teaching delivery ID/投影 SHA-256、route task 与 response decision fingerprint；追加后的 active resolution 还必须把它列为最后一条 process ref 且状态为 ready，只有这时可以开题，不能绕过未见 A0 验证；
- teaching delivery 的 `issued_at` 必须取真实当前时钟且不在未来；当前时刻若不能严格晚于 resolution 就失败重试，禁止用 `resolved_at + 1s` 制造顺序；
- 所有 diagnostic、teaching_process、verification、retention 提交都经过同一 `append-evidence` 事务：从 canonical session 反查来源、派生资格/置信度/消费者与 field bindings、重算同 scope state 和全部 boundary、标记旧 Focus stale；过程记录刷新 process refs/status、反馈、修复输入与成本，但保留作答前 decision epoch，真正换活动需显式 resolve + 重新签发。任一步失败必须精确回滚；完整合同满足时只返回 `route_reissue_required`，不得在证据事务中伪造下一 route issuance；
- 响应画像必须既被写入，也在下次同情境活动选择中被读取；
- `immediate_contract_status`、`retention_status` 与完整 `contract_status` 分开重算；即时满足且保持待定只进入保持安排，不能误回概念修复；
- retention 先追加 schedule receipt，due 开题前再追加或幂等复用 open receipt；两类 receipt 必须 exact metadata allowlist + full-metadata fingerprint + canonical body，open 不得保存题面/答案/`user_task`。state 只指当前 schedule，历史 evidence 按自己的 open→schedule→issuance 校验。保持失败必须经过更新且合格的新 verification baseline、新 task/binding 和 superseding schedule，不能停在永久 pending；
- `issue-route.expected_chain_head` 与 `schedule-retention.expected_state_evaluated_at` 是 CAS 前置条件；漂移时必须零写入。所有生产 writer 在同一外部跨进程 Vault 锁内完成 read/CAS/write/validate/rollback，锁超时零写入；所有写后失败都要求仍持锁的全树 byte-exact 回滚。

每次发布版本都必须创建使用完整版本号命名的新 `.mmd + .png`，更新 `SKILL.md` 中的内联图片，并保留 `ELD` 水印与版权标记。默认只递增补丁号；次版本和主版本必须由版权所有者明确指定，不能由维护者自行判断。流程图通过审阅后，才允许同步发布包或推送远端；缺少版权所有者对该次外部发布的明确授权时，只能停留在本地。

## 路由恢复

```powershell
py -3 -X utf8 scripts\vault_tool.py recover-learning-route --vault <精确绝对Vault路径> --data-mode use_existing --confirmation-ref <实际用户消息引用> --data-root <同一精确绝对Vault路径>
```

该命令默认只读。未找到旧数据时不得自动创建新 Vault；多条活动路线或支线歧义必须让用户选择。缺少精确位置先询问用户，不运行旧的向父目录扫描命令。

## 当前边界

- “理解成本”是工程化工作定义，不是公认心理量表；
- Focus Cone 是 Agent 内部实验视图，不代表能力或教学效果已被验证；
- Demo 数据为合成数据；真实学习结论必须来自同范围行为证据；
- evidence 的 `source_kind/source_ref` 必须从其唯一 canonical session 反查；本地 session 和 evidence 同时被协同改写仍超出无密钥本地校验能力，真实来源真实性需要宿主 receipt 或签名；
- active resolution 是可重算缓存：生产 `write=True` 禁止 caller 提供 `_as_of`。process 绑定作答前 teaching delivery 的 response decision fingerprint；刷新后的 resolution 用 `resolved_process_refs/status` 接纳该记录，不能反过来要求 process 晚于刷新后的 `resolved_at`。无外部单调 receipt 时，不声称能抵抗对历史 resolution 与全部本地 evidence 的协同回拨；
- 发布前重新运行结构校验、回归测试和 SkillHub `publish --dry-run`。
