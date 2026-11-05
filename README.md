# Architecture Gym

运行在 Codex、Claude Code 等 Coding Agent 中的自适应软件架构训练 Skill。通过有限轮次的设计、演进与复盘，训练抽象发现、变化预测、复杂度控制、正确性建模和技术取舍。

**不预装固定题库。** 每次需要新题时，Builder 实时检索 GitHub 上高 star、awesome 列表收录的项目，从 RFC、ADR、Issues、PR 和提交历史中寻找适合玩家的设计决策。热度只用于发现候选，证据质量与训练适配决定是否出题。

## 安装与开始

需要 Python 3.9+；在线 GitHub 发现脚本需要已登录的 `gh`，也可由宿主检索工具替代。脚本只用标准库，不需要 pip、数据库或模型 API Key。

```sh
gh repo clone reyoung/arch-gym
```

将仓库中的 `architecture-gym/` 目录复制到 Coding Agent 的技能目录，例如：

- Codex：`~/.agents/skills/architecture-gym/`
- Claude Code：`~/.claude/skills/architecture-gym/`
- Minis：`/var/minis/skills/architecture-gym/`

也可以让 Agent 直接读取 [SKILL.md](architecture-gym/SKILL.md) 并遵循其流程。示例请求：

> 使用 Architecture Gym。我熟悉 Python，但不熟悉分布式系统，来一局架构设计训练。

> Use Architecture Gym. Start at L3 and focus on state ownership. Use historical evidence where available.

首次会确认影响选题的背景，然后构建或选择案例。默认 3–5 轮，可随时结束、简化或下次继续。玩家无需猜中项目真实方案。

## 工作方式

1. 读取本地画像和历史，优先续玩，排除已暴露决策和近期相似冲突。
2. 隔离的 Case Builder 发现候选、核对历史、生成 3–5 轮 JSON 并缓存。
3. Coach 通过脚本获取当前轮信息，记录回答、知识提问和设计提示。
4. 最终揭示真实选择或模拟参考方案，按行为证据复盘并更新画像。

Historical Replay 保留可追溯时间线；Sandbox 可以模拟合理变化；Toy 是 sandbox 模式下的小代码题。历史资料不足时明确说明，不补写虚构历史。知识障碍会触发解释和简化建议，不自动认定架构能力不足。两局不同冲突的充分独立表现才触发下一局升级。

Builder 与 Coach 应使用隔离子代理或独立会话。脚本裁剪输出不是文件权限沙箱；没有隔离能力时需使用已审核缓存、独立构建会话或明确披露限制的沙盘模式。

## 文件与命令

```text
architecture-gym/
├── SKILL.md
├── references/             # 游戏、难度、评分、检索及构建契约
├── scripts/
│   ├── discover_sources.py # GitHub / awesome 候选发现
│   ├── gym.py              # 选题、去重、分轮、恢复、记录、画像
│   └── validate_case.py    # 生成案例的结构校验
└── tests/                  # 状态和检索边界测试；非可玩题库
```

从 `architecture-gym/` 执行：

```sh
python3 scripts/discover_sources.py --topic database --min-stars 1000 --limit 8
python3 scripts/gym.py --player local-user profile
python3 scripts/gym.py --player local-user select
python3 scripts/gym.py --player local-user resume
python3 scripts/validate_case.py /path/to/generated-case.json
python3 -m unittest discover -s tests -v
```

完整操作见 SKILL.md。空缓存的 `needs_case` 表示应委托 Builder 取材，不是错误。状态默认保存在 `~/.local/share/architecture-gym/players/<player>.json`，案例保存在同级 `cases/`；支持 `--state-dir` / `--cache-dir` 覆盖。玩家记录包含回答，不应提交到仓库。一个玩家文件采用原子写入，活动局保存案例快照，支持多个独立玩家。

## MVP 边界

实现了可执行的发现、记录、去重、难度升级和结构校验，题目生成、历史核实、语义去重和行为评价由宿主 Agent 完成。校验器不能证明史料真实，star 或 awesome 引用也不证明设计优秀。没有自动爬取全部 RFC、执行外部项目代码或复杂评分服务。

自动测试验证确定性机制；真实对话体验仍需在目标 Agent 中按 [验收场景](architecture-gym/references/game-rules.md) 试玩。优秀的玩家可以提出比历史实现更好的方案，Coach 应识别并解释其成立条件。
