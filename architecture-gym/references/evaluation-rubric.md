# architecture-rubric-v1

评分对象是推理过程，不是与参考答案的相似度。先列可观察行为，再评维度；玩家质疑预设抽象并给出满足约束的更好模型，可以比历史方案得到更高评价。不要根据语言熟练度、术语知识、方案长度或框架数量评分。

| 维度 | 可观察行为 |
|---|---|
| abstraction_discovery | 从多个需求找稳定机制，区分业务概念、策略与机制 |
| change_prediction | 说明可能变化和受影响的模块、接口、数据 |
| complexity_management | 控制状态、接口、依赖及维护负担 |
| tradeoff_reasoning | 给出收益、代价、备选及选择条件 |
| correctness_modeling | 明确不变量、失败、边界和验证方法 |
| architectural_judgment | 知道何时抽象、何时保留简单设计，愿意修正 |

每维 0–4 行为锚点：

- 0：在有明确答题机会且已作设计回答后，仍未识别关键问题。**没有观察机会不是 0**。
- 1：明显提示后识别。
- 2：独立识别但分析不完整；或得到提示后有较完整分析，标注帮助程度。
- 3：独立识别并说明合理取舍、关键约束。
- 4：主动预测变化，并给出可验证的设计依据。

每维同时记录 assistance（independent/light/repeated/unobserved）和 confidence（low/medium/high）。少量提示后作答不能描述为独立；工具保守地拒绝引用设计提示之后的回答却标 independent。背景解释不属于设计提示。某维只在提示前观察到的独立回答可以引用其事件 ID 单独评价。

证据不足填 `score: null` 并说明缺失；不输出小数、总排名或未经验证的能力百分位。有限单题只能提供局部证据。对于分数争议，回到原始发言和约束，对合理反驳修正评价，不维护预设答案。

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
      "reason": "没有足够观察机会",
      "event_ids": []
    }
  }
}
```

非 null 分数至少引用一个实际保存的 answer 事件。事件 ID 由 event/resume 输出给出，不能编造。其余五个维度使用同样形状。然后运行：

```sh
python3 scripts/gym.py --player PLAYER finish --assessment /path/to/assessment.json --reason completed
```

主动结束或缺少评价时间可不传 assessment；默认全部 null，并正常保存退出和揭晓记录。`completed` 表示教学目标已完成，可早于最后一轮；`stopped`/`switched`/`evidence-gap` 不作为完成局触发升级。

## 最终复盘

按“你的设计及依据 → 变化造成的代价 → 真实/参考方案与可替代选择 → 一个可迁移的原则”简短展开。引用本局具体判断，最终给出原始来源链接、历史完整性/争议和结果能否验证。沙盘明确说参考方案未经真实生产结果验证。不要把真实方案的采用本身当作胜负依据。
