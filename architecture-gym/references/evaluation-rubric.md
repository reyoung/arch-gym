# architecture-rubric-v1

评分对象是推理过程，不是与参考答案的相似度。先列可观察行为，再评维度；玩家质疑预设抽象并给出满足约束的更好模型，可以比历史方案得到更高评价。不要根据语言熟练度、术语知识、方案长度或框架数量评分。

| 维度 | 可观察行为 |
|---|---|
| abstraction_discovery | 从多个需求找稳定机制，区分业务概念、策略与机制 |
| change_prediction | 说明可能变化和受影响的模块、接口、数据 |
| complexity_management | 控制状态、接口、依赖及维护负担 |
| tradeoff_reasoning | 说明实际竞争目标、收益、代价及选择条件；存在可信备选时比较，不按选项数量计分 |
| correctness_modeling | 明确不变量、失败、边界和验证方法 |
| architectural_judgment | 知道何时抽象、何时保留简单设计，愿意修正 |

每维 0–4 行为锚点：

- 0：在有明确答题机会且已作设计回答后，仍未识别关键问题。**没有观察机会不是 0**。
- 1：明显提示后识别。
- 2：独立识别但分析不完整；或得到提示后有较完整分析，标注帮助程度。
- 3：独立识别并说明合理取舍、关键约束。
- 4：主动预测变化，并给出可验证的设计依据。

每维同时记录 assistance（independent/light/repeated/unobserved）和 confidence（low/medium/high）。实际设计提示使用 hint 留痕，受提示后作答不能描述为独立。中性追问、背景解释和契约澄清不属于设计提示；不要仅因 Coach 追问就把初始独立答案标为 light。某维只在提示前观察到的独立回答可引用原事件单独评价。

简洁且依据充分的回答可以得到高分；不要求把已清楚表达的判断扩写。若需确认未表达的依据，可中性追问，不能把“未展开”直接判作“不会”。题目没有可信替代方案时，不因未列备选扣分；有明确取舍的可按收益、代价与边界评分，没有足够观察机会的维度填 null。确认接口契约、失败语义或题目范围是 clarification，不是领域无知；knowledge-question 仅记录真正的概念困惑，次数不直接决定能力分。

证据不足填 `score: null` 并说明缺失；不输出小数、总排名或未经验证的能力百分位。有限单题只能提供局部证据。对于分数争议，回到原始发言和约束，判断反驳是否成立，不维护预设答案，也不自动附和。

## 写入格式

结束前把以下形状写为 UTF-8 JSON，`dimensions` 必须有上述六个键；为每个键填写独立对象。不要将省略符原样写入文件。

```json
{
  "summary": "本局观察到的行为、主要取舍与下一次训练建议",
  "dimensions": {
    "abstraction_discovery": {
      "score": null,
      "confidence": "low",
      "assistance": "unobserved",
      "evidence_phase": "in-game",
      "reason": "没有足够观察机会",
      "event_ids": []
    }
  }
}
```

其余五个维度使用同样形状；初评与替换评价都必须含全部六维，不接受局部补丁。局内回答证据使用 `"evidence_phase": "in-game"`；只有已定案且属于 in-game 的评价证据可用于能力观察或升级，仍需满足独立性、信心等条件。初评非 null 分数至少引用一个实际保存的 answer 事件。事件 ID 从 event/resume/review 等工具输出获取，不能编造。复核评价可以引用已保存的 rebuttal 事件；任何维度只要引用揭晓后的反驳事件，就须增加 `"evidence_phase": "post-review"`，即使同时引用原 answer 也不能算自动升级或独立画像证据。此类证据可展示复盘后的理解，不能冒充独立解题表现。若只纠正对原回答的误读，引用原 answer 作为评分依据即可，不必把促使重新检查的反驳当作该维能力证据。

然后运行：

```sh
python3 scripts/gym.py --player PLAYER finish --assessment /path/to/assessment.json --reason completed
```

主动结束或缺少评价时间可不传 assessment；默认全部 null，并正常保存退出和揭晓记录。finish 结束轮次并揭示参考；只有 completed 将初评标为 `review_status: pending`，此时不影响画像或自动等级。stopped/switched/evidence-gap 直接定案，不要求额外复核才能停止或切换，但之后仍可用 rebuttal 重开。`completed` 表示教学目标已完成，可早于最后一轮，不等于评价已定案；`stopped`/`switched`/`evidence-gap` 不作为完成局触发升级。

## 复核与定案

`gym.py review [--session-id ID]` 展示复盘、当前评价、事件及修订历史。`gym.py rebuttal --text TEXT [--session-id ID]` 保存玩家反驳原话，已定案对局会重新待复核。纠正较早对局，尤其已开新局时，显式指定该局 ID。不要把反驳伪装为揭晓前 answer。

核对每条异议与原题约束、事件、实际提示：有效则接受；部分有效则分别处理；错误则给出可核实的反证，不自动同意、不增加事后约束。证据缺失就承认未知。通常 1–2 次往返，无需额外批准才可反思或不同意。

用 `gym.py resolve-review --disposition upheld|revised|uncertain|accepted|skipped --reason TEXT [--assessment PATH] [--session-id ID]` 收束；执行时选择一个 disposition：

| disposition | 适用情况与评价处理 |
|---|---|
| upheld | 核对原约束和事件后维持原评，reason 说明具体依据；不声称玩家同意。 |
| revised | 反驳全部或部分成立，提交完整六维替换评价，reason 指明修订依据。 |
| uncertain | 现有证据无法定论，提交完整替换评价，将受影响维度按证据降低信心或置 null，注明未知。 |
| accepted | 玩家明确认可当前评价，保留当前评价。 |
| skipped | 玩家选择停止或下一局而未认可，不强迫接受；保留当前评价和未决异议说明。 |

revised 和 uncertain 必须给 `--assessment PATH`，不能只提交变动维度。所有定案保留先前评价审计，修订不覆盖历史；重开复核期间该局评价不作为已定案画像证据。定案后按当前评价、证据阶段及难度策略计算画像，不重复累计同局旧评。skipped 表示结束讨论，不是证明争议已解决，仍须使用原有信心与证据限制。

待复核时 resume 返回复盘，select/start 必须等待 resolve-review。用户停止或要求下一局时，明确认可才用 accepted，否则 skipped，简短说明收束即可，不再次索要认可。

## 最终复盘

按“你的设计及依据 → 变化造成的代价 → 真实/参考方案与有意义的替代选择（若存在）→ 一个可迁移的原则”简短展开，明确当前为初评。引用本局具体判断，给出原始来源链接、历史完整性/争议和结果能否验证。沙盘明确说参考方案未经真实生产结果验证。不要把真实方案的采用本身当作胜负依据。

正常复盘以“哪些评价你不同意，或有哪些取舍我漏看了？也可直接结束。”结束；用户已要求停止则只短评并收束复核，不再提问。对局反馈应先核实，再归纳为可复用问题，例如错误计数澄清、按字数推断能力、虚构备选或低估题目过易；仅在用户授权范围内修改教学规范，不自动把未经证实的抱怨写成新规则。
