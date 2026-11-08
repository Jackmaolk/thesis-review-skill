# 维护指南

这个仓库是**自己用 + 持续改进**的。下面说明怎么改、怎么发。

---

## 两个目录的关系

```
E:\deepseekharness\.agents\skills\thesis-review-comments\   ← 本地工作版（含真实姓名）
E:\deepseekharness\repo_thesis_review\                     ← 公开仓库版（已脱敏）
```

**永远改本地版，然后用脚本同步过去。**

---

## 日常维护流程

### 改了点东西，想发布

```bash
cd E:\deepseekharness\repo_thesis_review
python publish.py "fix: 修正图片检测漏判"
```

`publish.py` 自动做五步：

```
1/5  同步本地 -> 仓库（自动脱敏）
2/5  脱敏检查 + 跑测试
3/5  git commit
4/5  git push
5/5  完成
```

**任何一步不过就停下，不会推坏东西。**

### 只想看看有没有差异

```bash
cd E:\deepseekharness\repo_thesis_review
python sync.py status
```

输出：

```
本地独有: 无
仓库独有: ['README.md', 'sync.py']
内容一致（本地脱敏后 == 仓库）
```

### 只想跑检查不发布

```bash
python sync.py verify
```

检查两件事：
1. 仓库里有没有泄露真实姓名
2. 测试是否全过

---

## 脱敏怎么工作

映射表放在 `E:\deepseekharness\repo_thesis_review\.sanitize.json`：

```json
{
  "老师批注名": "Teacher",
  "学生姓名": "Student",
  "另一个学生": "Student",
  "学校名称": "示例大学"
}
```

**这个文件在 `.gitignore` 里，永远不会被提交。**

添加新的替换项：

```bash
# 编辑 .sanitize.json，加一行就行
```

---

## 常见维护场景

### 场景 1：发现批注判断错了

1. 改 `references/反误判清单`（如果有这个文件）或 SKILL.md 里的禁止项
2. 在 `tests/test_pipeline.py` 加一条测试
3. `python publish.py "fix: 补充XX误判规则"`

### 场景 2：学校格式要求变了

只需要改 `rules.yaml`（本地那份，不进仓库）。**代码不用动。**

### 场景 3：想加新功能

```bash
# 1. 在本地版加脚本
# E:\deepseekharness\.agents\skills\thesis-review-comments\scripts\新功能.py

# 2. 加测试
# tests/test_pipeline.py 里加一个 test_xxx()

# 3. 跑通
python tests\test_pipeline.py

# 4. 发布
cd E:\deepseekharness\repo_thesis_review
python publish.py "feat: 新增XX功能"
```

### 场景 4：别人提了 issue

```bash
gh issue list --repo Jackmaolk/thesis-review-skill
gh issue view <编号> --repo Jackmaolk/thesis-review-skill
# 改完发布后回复
gh issue comment <编号> --repo Jackmaolk/thesis-review-skill --body "已修复，见 vX"
```

---

## 应急：误传到仓库了

**如果真实姓名或学生论文被误提交：**

```bash
cd E:\deepseekharness\repo_thesis_review

# 1. 撤销跟踪
git rm --cached 误传的文件
git commit -m "fix: 移除误传文件"

# 2. 彻底从历史删除
$env:FILTER_BRANCH_SQUELCH_WARNING='1'
git filter-branch --force --index-filter \`
  "git rm --cached --ignore-unmatch 误传的文件" \`
  --prune-empty -- --all

# 3. 清理并强推
Remove-Item .git\refs\original -Recurse -Force
git reflog expire --expire=now --all
git gc --prune=now
git push --force origin master
```

**注意：force push 会改写历史，如果别人已经 fork 了，他们需要重新 fork。**

---

## 当前状态

```
仓库  https://github.com/Jackmaolk/thesis-review-skill
分支  master
测试  13/13 通过
脱敏  干净
文件  26 个
```

---

## 版本记录

| 提交 | 内容 |
|---|---|
| 0b50b19 | 首次发布：技能 + 脚本 + 文档 + 截图 |
| 后续 | 加 sync.py / publish.py / 维护指南 |

---

## 一句提醒

**这个技能最值钱的部分不是代码，是 `references/` 里的反误判清单。**

每发现一个误判，就加一条进去。加得越多，下次越准。