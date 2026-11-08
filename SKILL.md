---
name: thesis-review-comments
description: 高校毕业论文导师审核。读学校格式规范与往期批注样本，学习批注者风格，在学生原 Word 文件对应位置插入原生批注（不修改正文），输出可复核的批注版。Use when 用户提到审论文、批注论文、导师审稿、格式审查、毕业论文、给论文加批注等。
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
license: MIT
---

# 导师审稿 Skills

把导师重复的审稿劳动变成可复用流程：**学风格 → 查事实 → 报清单 → 写批注 → 验结果**。

**铁律：只批注，不改正文。**

---

## 一、首次配置（每人一次）

### 1.1 目录结构

```
论文审核/
├── 00_标准/
│   ├── rules.yaml          学校格式规则
│   └── profile.yaml        ★你的批注风格（learn_style 生成）
├── 01_范文/                往届优秀论文
├── 02_批注样本/            ★你批注过的论文
├── 03_待审/                本届学生论文
└── 04_输出/                批注版 + 报告
```

### 1.2 学习批注风格

把 5-20 篇你批注过的论文（.docx 或 .doc）放进 `02_批注样本/`，然后：

```bash
python scripts/learn_style.py --samples ./02_批注样本 --out ./00_标准/profile.yaml --name "你的名字"
```

输出示例（实测 16 篇 / 162 条）：

```yaml
name: "Teacher"
samples: 162
files: 16
length:
  mean: 19.6       # 平均 19.6 字
  min: 1
  p50: 12
  p90: 42
tone:
  imperative_pct: 69.8   # 70% 命令式
  strength: 4            # 语气强度 4/5
phrases:
  reject: ["都改", "全改", "重新写", "重写"]
  complain: ["太少", "看不清", "太多"]
  reference: ["参考论文", "看群里"]
  minimal: ["改", "单独一页", "断表"]
habits:
  no_explain: true       # 不解释理由
  minimal_pct: 13.0      # 13% 是 4 字以内
```

**这个画像决定后续所有批注的语气。换人用就重新学。**

### 1.3 格式规则

```yaml
kinds:
  h1:   {name: "章标题", font: 黑体, size: 15, bold: false}
  h2:   {name: "二级标题", font: 黑体, size: 14}
  h3:   {name: "三级标题", font: 黑体, size: 13}
  body: {name: "正文", font: 宋体, size: 12, firstLine: "480"}
  caption: {name: "图表题注", font: 黑体, size: 11}
  ref:  {name: "参考文献", font: 宋体, size: 10.5}
```

---

## 二、每篇论文六步流程

### Phase 0 - 备份 + 事实核查（不可跳过）

```bash
python scripts/backup.py "03_待审/张三.docx"
python scripts/fact_check.py "03_待审/张三.docx"
```

`backup.py`：复制到 `_批注备份/`、校验 ZIP、校验批注锚点。

`fact_check.py` 输出客观数据，**不做判断**：

```json
{
  "word_count": {"ch1": 4134, "ch2": 3381, "ch5": 1316, "ch6": 7549},
  "abstract_words": 678,
  "figure_count": 25,
  "table_count": 17,
  "citations": {"ch1": 6, "ch2": 9, "ch3": 0, "ch4": 0},
  "captions_misplaced": [],
  "chapters_without_break": []
}
```

> **没有这些数据，不许写任何批注。**

### Phase 1 - 生成候选清单

按 `references/批注规则.md` 逐章扫描。每条候选必须带：

- 段落号
- 原文片段
- **客观依据**（字数/图数/引用数/具体缺失）
- 严重度：致命 / 重要 / 次要

**要深入章节中间和结尾，不能只批章节开头。**

### Phase 2 - ★检查点：给用户确认

把清单打印给用户勾选：要批 / 不批 / 改措辞。

> 这一步防止 AI 误判。宁可多问一次，不要批错返工。

### Phase 3 - 写入批注

```bash
python scripts/wps_center.py plan.json
```

plan.json：

```json
{
  "author": "你的名字",
  "delay": 2000,
  "center": 9,
  "issues": [
    {"para": 114, "text": "381字全是定性描述，一个数据都没有。给个数。"},
    {"para": 365, "text": "功能测试6条，第5章列了17个功能，覆盖不住。"}
  ]
}
```

参数：
- `para` - 段落索引，从 fact_check 结果里找
- `delay` - 每条停留毫秒（2000 = 2 秒）
- `center` - 向上滚动行数，让目标落在屏幕中间

**为什么用 para 不用 find**：`find` 按文字搜，目录里也有同名条目，会锚错位置（实测踩过 3 次）。`para` 是段落索引，绝对准。

### Phase 4 - 校验

```bash
python scripts/audit_comments.py "04_输出/张三_批注版.docx"
```

必须全部通过：

```
批注 21 | start 21 | end 21 | ref 21   <- 四项必须相等
空段锚点 0                              <- 不能在空段落
批注作者 == 你的名字
```

### Phase 5 - 出报告（可选）

```bash
python scripts/make_report.py "03_待审/张三.docx" "00_标准/rules.yaml" "04_输出/审核报告.docx"
```

---

## 三、反误判清单（最重要）

这些坑全部真实发生过：

| 错误批注 | 实际 | 正确做法 |
|---|---|---|
| 第一章内容太少 | 实际 3756 字 | 先数字数 |
| 4.4太薄 | 实际 644 字 | 先数字数 |
| 结论太少 | 实际 937 字 | 先数字数 |
| 图太小看不清 | 图是清晰的 | 先看图 |
| E-R图要拆开 | 已拆成 15 张 | 先数图 |
| 图4.2题注在上方 | 就在下方 | 先看位置 |
| 1.2没文献 | 有 [3][4] | 先查引用 |
| 第二章没小标题 | 已有 2.1-2.6 | 先看结构 |
| 19张表不是三线表 | 18 张合格 | 看 tcBorders |

### 硬规则

1. 任何判断必须有 fact_check 数据支撑
2. 拿不到数据就写待确认，不下结论
3. 禁止统计表述：41个里37个没问题 -> 一眼 AI
4. 禁止只批章节开头，必须深入中间结尾
5. 同一位置最多 1 条，相关问题合并
6. 每章都要有批注

### DOCX 技术坑

| 坑 | 表现 | 解法 |
|---|---|---|
| 图片格式多样 | 漏判图片导致误判题注位置 | 同时检测 w:drawing / w:pict / w:object / v:imagedata |
| 三线表边框在单元格 | 误判没有三线表 | 看 w:tcBorders，不是 w:tblBorders |
| 目录同名 | 批注锚到目录 | 用段落索引，不用文字搜索 |
| 删批注留孤儿锚点 | WPS 显示空批注 | 删时同步清 RangeStart/End/Reference |
| ZIP 未关闭 | Windows 文件被占用 | 用完调 close_analysis() |

---

## 四、批注语气

读 `00_标准/profile.yaml`：

| 画像项 | 怎么用 |
|---|---|
| length.mean | 平均字数，别偏离太多 |
| length.min | 允许极简（改、同上） |
| tone.imperative_pct > 60% | 用命令式：全改、重写 |
| tone.strength 4-5 | 可以带感叹号 |
| habits.no_explain | 不解释为什么 |
| phrases.reject | 直接用这些词 |
| phrases.minimal | 这些场景用极简批注 |

**对比：**

像导师说的：
> 图表都重新做，看不清，拆成小图。

AI 味：
> 该处图表清晰度不足，建议作者将其拆分，以提升可读性。

---

## 五、脚本清单

| 脚本 | 作用 | 何时用 |
|---|---|---|
| learn_style.py | 从历史批注学风格 | 首次配置 |
| backup.py | 备份+校验 | 每篇开始前 |
| fact_check.py | 事实核查 | 每篇开始前 |
| wps_center.py | 写入批注+居中滚动 | 确认清单后 |
| wps_apply.py | 写入批注（无 UI） | 批量处理 |
| wps_anchor.py | 段落定位 | 被上面调用 |
| format_check.py | 格式规则检查 | 辅助 |
| audit_comments.py | 批注体检 | 写完必跑 |
| verify_integrity.py | 正文完整性 | 写完必跑 |
| make_report.py | 生成审核报告 | 可选 |

---

## 六、自测

```bash
python tests/test_pipeline.py
```

13 项全部通过才算环境正常。

---

## 七、给别人用

1. 复制技能目录到 `.agents/skills/`
2. 建好目录结构
3. 放学校格式规范 -> 写 rules.yaml
4. 放 5-20 篇历史批注 -> 跑 learn_style.py
5. 之后每篇按六步流程

**每个人风格画像不同，这就是自适应学习。**