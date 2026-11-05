# 运行时案例数据契约

案例在运行时检索与生成，不随技能打包。技能目录的 `cases/` 不存放具体可玩案例。生成器将 UTF-8 JSON 写入外部缓存 `<cache-dir>/<id>.json`；运行时通过 `--cache-dir` 选择缓存，默认 `~/.local/share/architecture-gym/cases`。下文的 `cache-dir` 已指向案例目录，不再拼接第二层 `cases` 或 `cache`。

## 顶层字段

所有下列字段都必须出现；没有数据时使用规定的 `null` 或空数组，不能以虚构信息补齐。除历史轮次的 `as_of` 外，不增加未列出的字段。

| 字段 | 类型与约束 |
| --- | --- |
| `id` | 非空 slug，匹配 `[a-z0-9][a-z0-9-]*`；同缓存内唯一，文件名为 `<id>.json`。优先中性 ID，避免泄露项目及结局。 |
| `title` | 非空字符串；内部案例标题，未结束时不直接向学习者展示。 |
| `mode` | `sandbox` 或 `historical-replay`。 |
| `kind` | `toy`、`sandbox`、`historical` 三种之一，映射见下表。 |
| `difficulty` | 整数 0..5；布尔值不是整数等级。难度取决于推理负担，不由项目规模决定。 |
| `source` | 下文规定的来源对象。 |
| `topics` | 非空字符串数组，标明领域或机制；不以 topic 代替学习目标。 |
| `core_conflict` | 非空、有意义的 slug，概括核心架构冲突，用于避免换皮重复。 |
| `prerequisites` | 字符串数组；无先修知识时可为空。 |
| `learning_objectives` | 从规定枚举选择；构建规范要求 2..3 个不重复目标。 |
| `initial_context` | `{description: string, constraints: string[], code: string|null}`；描述非空，代码可空，不含未来需求或答案。 |
| `rounds` | 3..5 个轮次对象，按学习者获得信息的顺序排列。 |
| `evidence` | 顶层证据对象数组；模拟案例必须为 `[]`。 |
| `reference` | 最终复盘对象，练习结束前不提供给教练或学习者。 |
| `simplifications` | `{difficulty: integer, case_id: string}` 数组；可为空，引用实际存在的较低难度案例。 |
| `evaluation` | 固定为 `{"rubric":"architecture-rubric-v1"}`。 |

| kind | mode | 含义 |
| --- | --- | --- |
| `toy` | `sandbox` | 原创小代码练习，仅在适合且用户需求覆盖或已同意时按需生成。 |
| `sandbox` | `sandbox` | 明确虚构的架构沙盘，约束与结果推断均不冒充项目历史。 |
| `historical` | `historical-replay` | 有可追溯来源的历史决策片段，按当时可获得的信息逐轮回放。 |

`toy` 不是第三种 mode，历史项目启发的虚构练习也不能标成 `historical`。

学习目标枚举：`abstraction_discovery`、`change_prediction`、`complexity_management`、`tradeoff_reasoning`、`correctness_modeling`、`architectural_judgment`。

## 来源与证据

`source` 必须恰有：

| 字段 | 类型与含义 |
| --- | --- |
| `repository` | 字符串或 `null`；历史案例使用可辨认的仓库名，如 `owner/repository`。 |
| `document` | 字符串；历史案例使用主讨论、RFC、ADR、PR 的稳定标识（如 `RFC-123`），用于跨会话去重；片段范围与遗漏放在 `completeness`，不要混入此标识。 |
| `url` | HTTPS URL 或 `null`；历史案例必须给出可追溯的主来源。 |
| `base_commit` | 已核实的完整 40 位十六进制 Git SHA 或 `null`；不能猜测、截短或用分支名代替。 |
| `completeness` | 非空字符串；说明证据覆盖与缺口。模拟案例固定为 `simulated`。历史案例明确“所选片段内完整”还是“存在已列明缺口”，不宣称覆盖整个项目历史。 |
| `disputed` | 布尔值；有未解决的来源冲突时设为 `true`，在来源说明或复盘中说明争议。 |
| `outcome_verifiable` | 布尔值；只有来源足以支持所陈述的结果时才设为 `true`。合并 PR 不自动证明生产收益。 |

模拟案例的来源固定为：

```json
{"repository":null,"document":"original teaching simulation","url":null,"base_commit":null,"completeness":"simulated","disputed":false,"outcome_verifiable":false}
```

历史案例的每条顶层 `evidence` 结构为：

```json
{"id":"e-placeholder","url":"https://example.invalid/source","date":"2000-01-01","summary":"<该来源在此日期已经公开的事实；必要时注明消息、提交或段落定位>"}
```

证据 ID 在案例内唯一。`date` 是该条所引用信息公开可得的日期，格式为 `YYYY-MM-DD`，不是抓取日，也不能用 issue 创建日替代多年后某条评论的日期。会持续编辑的文档应使用固定提交链接或可核对的版本；无法还原当时内容则明确缺口。日期粒度不足以区分同日先后时，人工核对原始时间与因果顺序；无法核实就合并轮次或移除相关主张，不能仅靠日期检查判定无剧透。

轮次和复盘的 `evidence` 只保存顶层证据 ID 字符串，不复制证据对象。每个历史轮次必须至少引用一条支持当前信息的证据；复盘同样必须有证据。仅有 URL、日期及摘要的正确结构，不能证明引用内容真实或足以支持结论。

## 轮次与复盘

所有轮次都有 `{stage, challenge, context, constraints, evidence}`：`stage` 是非空阶段名；`challenge` 是一条主问题；`context` 是字符串；`constraints` 是字符串数组；`evidence` 是证据 ID 数组。历史轮次还必须有 `as_of: "YYYY-MM-DD"`，各轮日期非递减，所引用证据的日期不能晚于该轮。模拟轮次不添加虚构历史日期。

第一轮只重述初始问题及当前约束，不偷带第二轮及之后的条件；后续每轮只引入有界变化，不通过无限加需求制造难度。历史轮次的约束必须确实在当时存在；教学性假设若改变了事实，应转为明确标注的模拟案例。`initial_context`、每轮正文、代码注释、符号名及被选择的证据摘要都要审查未来信息泄露。

`reference` 必须恰有：

- `actual_decision: string`：历史案例如实区分讨论、提议、采纳和落地；模拟案例明确写“参考选项，并非真实历史决策或唯一答案”。
- `alternatives: string[]`：多个在给定约束下可辩护的方案及适用条件。
- `tradeoffs: string[]`：具体收益、成本、风险及成立前提；不能以“与历史一致”代替论证。
- `outcome: string`：模拟案例必须以“模拟情景，未观察真实生产结果。”开头，再给出可验证的预期或验收方式；历史案例区分已观察结果、作者陈述、推断与未知。
- `evidence: string[]`：支撑最终决策及结果的证据 ID；模拟案例为 `[]`。

`simplifications` 的目标难度必须更低，至少保留一个学习目标，并保留待训练的核心冲突。只引用同一缓存内已生成且验证通过的目标；没有目标时用 `[]`，不要为了补链条生成未获同意的 toy。

## 字段骨架：不是可玩案例

以下仅展示模拟分支的字段位置。尖括号内容是占位符，不得加入案例缓存或当作验证通过的教学内容。真实生成时填入 3..5 个有实际内容的轮次；历史分支按上述规则更换来源、补证据和 `as_of`。

```json
{
  "id": "replace-before-use",
  "title": "<内部标题>",
  "mode": "sandbox",
  "kind": "sandbox",
  "difficulty": 0,
  "source": {
    "repository": null,
    "document": "original teaching simulation",
    "url": null,
    "base_commit": null,
    "completeness": "simulated",
    "disputed": false,
    "outcome_verifiable": false
  },
  "topics": ["<主题>"],
  "core_conflict": "replace-conflict",
  "prerequisites": [],
  "learning_objectives": ["abstraction_discovery", "tradeoff_reasoning"],
  "initial_context": {
    "description": "<当前已知的问题>",
    "constraints": ["<当前约束>"],
    "code": null
  },
  "rounds": [
    {"stage":"initial-design","challenge":"<一个主问题>","context":"<仅初始信息>","constraints":[],"evidence":[]},
    {"stage":"bounded-evolution","challenge":"<一个主问题>","context":"<有界的新信息>","constraints":[],"evidence":[]},
    {"stage":"decision-review","challenge":"<一个主问题>","context":"<最终检查所需的信息>","constraints":[],"evidence":[]}
  ],
  "evidence": [],
  "reference": {
    "actual_decision": "参考选项，并非真实历史决策或唯一答案：<条件与方案>",
    "alternatives": ["<可辩护选项一>", "<可辩护选项二>"],
    "tradeoffs": ["<具体取舍及前提>"],
    "outcome": "模拟情景，未观察真实生产结果。<预期验收方式>",
    "evidence": []
  },
  "simplifications": [],
  "evaluation": {"rubric":"architecture-rubric-v1"}
}
```

## 验证边界

从技能根目录运行 `python scripts/validate_case.py <path>`，成功状态才允许缓存案例进入运行时。结构验证包括字段、类型、枚举、3..5 轮、引用完整性、模式映射及历史日期关系；跨案例简化引用还需对实际缓存检查。若当前验证器没有实现本文某项约束，构建者仍须人工检查，不能把工具通过当作该项已经验证。

来源真实性、证据是否支持主张、历史完整性、日期语义、难度适配、合理替代方案、提示注入与剧透检查属于语义审查。结构通过不等于来源已核实，更不等于历史方案是标准答案。
