# -*- coding: utf-8 -*-
"""make_report.py —— 生成审核报告.docx"""
import sys, os, datetime
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import yaml
from format_check import check

def setf(run, cn='宋体', size=12, bold=False):
    run.font.name = 'Times New Roman'; run.font.size = Pt(size); run.font.bold = bold
    run._element.rPr.rFonts.set(qn('w:eastAsia'), cn)

def P(doc, text, cn='宋体', size=12, bold=False, indent=True, align=None, space_after=6):
    p = doc.add_paragraph()
    if indent: p.paragraph_format.first_line_indent = Pt(size*2)
    if align: p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    setf(p.add_run(text), cn, size, bold)
    return p

def main(src, rules_path, out, teacher='', content_issues=None):
    rules = yaml.safe_load(open(rules_path, encoding='utf-8'))
    paras, issues = check(src, rules)
    doc = Document()
    s = doc.sections[0]
    s.top_margin = Cm(2.5); s.bottom_margin = Cm(2.5)
    s.left_margin = Cm(3.0); s.right_margin = Cm(2.5)

    P(doc, '毕业论文审核报告', '黑体', 18, True, indent=False,
      align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    name = os.path.splitext(os.path.basename(src))[0]
    P(doc, '受审论文：' + name, '宋体', 10.5, False, indent=False,
      align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    P(doc, '审核日期：' + datetime.date.today().isoformat(), '宋体', 10.5, False,
      indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=16)

    # 一、总体情况
    P(doc, '一、总体情况', '黑体', 14, True, indent=False, space_after=6)
    total = len(paras)
    fmt_n = len(issues)
    cnt_n = len(content_issues or [])
    concl = '格式方面共发现 %d 处问题，内容方面提出 %d 条意见。' % (fmt_n, cnt_n)
    P(doc, concl)
    if fmt_n == 0:
        P(doc, '格式抽查未见明显偏差。')
    else:
        bad = [p['idx'] for p in paras if p['text'].strip()]
        ratio = fmt_n / max(1, len(bad))
        lvl = '较好' if ratio < 0.1 else ('一般' if ratio < 0.25 else '较差')
        P(doc, '格式符合度评价：%s（问题段落占正文段落约 %.0f%%）。' % (lvl, ratio*100))

    # 二、格式问题
    P(doc, '二、格式问题清单', '黑体', 14, True, indent=False, space_after=6)
    if not issues:
        P(doc, '本次抽查未发现格式偏差。')
    else:
        t = doc.add_table(rows=1, cols=4); t.style = 'Table Grid'
        hdr = ['序号', '位置（段落）', '问题', '规范要求']
        for i, h in enumerate(hdr):
            c = t.rows[0].cells[i]; c.text = ''
            setf(c.paragraphs[0].add_run(h), '黑体', 10.5, True)
        for k, it in enumerate(issues, 1):
            row = t.add_row().cells
            vals = [str(k), '第 %d 段' % (it['para']+1),
                    it['type'], str(it['expect'])]
            for i, v in enumerate(vals):
                row[i].text = ''
                setf(row[i].paragraphs[0].add_run(v), '宋体', 10)

    # 三、内容意见
    P(doc, '三、内容意见', '黑体', 14, True, indent=False, space_after=6)
    if not content_issues:
        P(doc, '详见原文批注。')
    else:
        for k, it in enumerate(content_issues, 1):
            P(doc, '%d. %s' % (k, it['text'].replace('【', '').replace('】', '：', 1)),
              '宋体', 12, False)

    # 四、修改要求
    P(doc, '四、修改要求', '黑体', 14, True, indent=False, space_after=6)
    P(doc, '1. 必须修改：文中已批注的格式偏差，逐条对照学校规范调整后重新提交。')
    P(doc, '2. 建议修改：内容部分标注“待核实”的意见，请补充材料或说明依据。')
    P(doc, '3. 修改稿请使用“修订模式”，便于核对改动。')
    P(doc, '4. 请在收到本报告后一周内提交修改稿。')

    doc.add_paragraph()
    P(doc, '审核人：' + (teacher or '＿＿＿＿＿＿'), '宋体', 12, False, indent=False,
      align=WD_ALIGN_PARAGRAPH.RIGHT)
    P(doc, '日期：' + datetime.date.today().isoformat(), '宋体', 12, False,
      indent=False, align=WD_ALIGN_PARAGRAPH.RIGHT)

    doc.save(out)
    print('报告已生成：', out)

if __name__ == '__main__':
    src, rules_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    teacher = sys.argv[4] if len(sys.argv) > 4 else ''
    main(src, rules_path, out, teacher)
