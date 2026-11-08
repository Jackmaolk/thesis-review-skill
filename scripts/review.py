# -*- coding: utf-8 -*-
import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))
import yaml
from format_check import check
from docx_comment import add_comments

src = sys.argv[1]; rules_path = sys.argv[2]; dst = sys.argv[3]
author = sys.argv[4] if len(sys.argv) > 4 else '导师'
initials = sys.argv[5] if len(sys.argv) > 5 else 'DS'
rules = yaml.safe_load(open(rules_path, encoding='utf-8'))
paras, issues = check(src, rules)

# 内容层：示例内容审查（真实系统里由模型产出，这里用规则兜底做端到端验证）
content = [
 {'para': 2, 'find': '能够满足所有用户需求',
  'text': '【内容·表述】“满足所有用户需求”过于绝对，且未给出依据。建议改为具体可达成的指标，如“覆盖学生信息增删改查、课程分配、成绩录入三类核心业务”，并补充第4章测试数据支撑。'},
 {'para': 2, 'find': '功能强大，用户体验良好',
  'text': '【内容·空泛】此处为结论性评价，正文尚无支撑。建议删除或后移至第5章，并用测试结果或用户反馈佐证。'},
 {'para': 13, 'find': '学生表、课程表、成绩表',
  'text': '【内容·待核实】正文列出的三张表与第2章所述“角色权限”无对应关系。若系统含角色管理，请补充角色表、用户角色关联表及其字段说明；若无，请说明权限控制的实现方式。'},
 {'para': 17, 'find': '如图所示',
  'text': '【内容·图文】此处“如图所示”未标注图号。正文引用图应写作“如图3-1所示”，且图3-1的题注需与本段描述一致。'},
 {'para': 21, 'find': '系统运行正常，没有发现明显问题',
  'text': '【内容·测试】仅有结论无过程。第4章应给出测试环境、测试用例表（编号/输入/预期/实际/结论）、边界与异常用例，并至少覆盖登录失败、越权访问两类场景。'},
]
for c in content:
    c['severity'] = 'B'

allc = issues + content
res = add_comments(src, dst, allc, author=author, initials=initials)
print(json.dumps({'added': res['ok'], 'skipped': res['skipped'], 'dst': dst}, ensure_ascii=False, indent=1))