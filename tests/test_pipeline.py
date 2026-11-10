# -*- coding: utf-8 -*-
"""
test_pipeline.py —— 端到端测试
验证：风格学习 → 事实核查 → 批注写入 → 完整性校验
"""
import sys, os, json, zipfile, re, shutil, tempfile
import gc
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 兼容三种布局：<root>/scripts、<root>/tools、脚本就在 <root>
for cand in (os.path.join(ROOT, 'scripts'), os.path.join(ROOT, 'tools'), ROOT):
    if os.path.isdir(cand) and any(f.endswith('.py') for f in os.listdir(cand)):
        if cand not in sys.path:
            sys.path.insert(0, cand)

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s' % (W, t.split(':')[1])

PASS, FAIL = [], []

def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + (('  ' + detail) if detail else ''))

# ── 1 风格学习 ──
def test_learn_style():
    from learn_style import extract_from_docx, build_profile
    samples = []
    # 造 3 条批注样本
    tmp = tempfile.mktemp(suffix='.docx')
    make_docx_with_comments(tmp, [
        ('全改。按最新要求改，字体字号逐级核。', '张老师'),
        ('图太小，打印出来看不清。拆分。', '张老师'),
        ('结论太少，多写点：出现什么问题、怎么解决的、怎么提升。', '张老师'),
        ('改', '张老师'),
    ])
    samples = extract_from_docx(tmp)
    os.unlink(tmp)
    check('能提取批注', len(samples) == 4, '实际 %d' % len(samples))

    prof = build_profile(samples, name='测试老师')
    check('算出平均长度', prof['length']['mean'] > 0)
    check('识别命令词', len(prof['phrases']['reject']) > 0 or len(prof['phrases']['complain']) > 0,
          str(prof['phrases'])[:40])
    check('识别极简批注', prof['length']['min'] <= 3, 'min=%d' % prof['length']['min'])
    return prof

# ── 2 事实核查 ──
def test_fact_check():
    from fact_check import analyze, close_analysis
    p = make_sample_paper()
    R, blocks, doc, z = analyze(p)
    check('识别正文起点', R['body_start'] > 0, 'body_start=%d' % R['body_start'])
    check('统计章节数', len(R['chapters']) >= 2, '%d 章' % len(R['chapters']))
    check('统计字数', sum(R['word_count'].values()) > 0, str(R['word_count']))
    check('统计图表', R['figure_count'] >= 0 and R['table_count'] >= 0,
          '图%d 表%d' % (R['figure_count'], R['table_count']))
    close_analysis(R)
    os.unlink(p)

# ── 3 批注写入 ──
def test_apply():
    from wps_apply import apply
    p = make_sample_paper()
    plan = {'author': 'T', 'comments': [
        {'para': 2, 'text': '测试批注一'},
        {'para': 3, 'text': '测试批注二'},
    ]}
    ok, miss, log = apply(p, plan, 'T')
    check('写入成功', ok == 2 and miss == 0, 'ok=%d miss=%d' % (ok, miss))

    z = zipfile.ZipFile(p)
    c = z.read('word/comments.xml').decode('utf-8')
    d = z.read('word/document.xml').decode('utf-8')
    z.close()
    del z
    check('批注数=锚点数',
          c.count('<w:comment ') == d.count('commentRangeStart') == d.count('commentRangeEnd')
          == d.count('commentReference'),
          '%d/%d/%d/%d' % (c.count('<w:comment '), d.count('commentRangeStart'),
                          d.count('commentRangeEnd'), d.count('commentReference')))

    # 空段检查
    R = None
    from fact_check import analyze as an
    R, blocks, doc2, zz = an(p)
    pmap = {pp['i']: pp['text'].strip() for pp in R['paras']}
    empty = 0
    for i, b in enumerate(blocks):
        if b.tag != q('w:p'): continue
        if b.findall('.//' + q('w:commentRangeStart')) and not pmap.get(i):
            empty += 1
    check('无空段锚点', empty == 0, '空段 %d' % empty)
    try:
        zz.close()
    except Exception:
        pass
    del zz
    import gc; gc.collect()
    os.unlink(p)

# ── 4 备份校验 ──
def test_backup():
    from backup import backup, verify
    p = make_sample_paper()
    dst, h, ok, msg = backup(p, 'unittest')
    check('备份成功', os.path.exists(dst) and ok, msg)
    check('SHA一致', verify(dst)[0])
    os.unlink(dst); os.unlink(p)

# ── 工具函数 ──
def make_docx_with_comments(path, comments):
    from docx import Document
    doc = Document()
    doc.add_paragraph('测试文档')
    for i, (txt, auth) in enumerate(comments):
        doc.add_paragraph('段落%d' % i)
    doc.save(path)
    # 手工注入批注
    zin = zipfile.ZipFile(path)
    items = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    root = etree.fromstring(items['word/document.xml'])
    body = root.find(q('w:body'))
    paras = [c for c in body if c.tag == q('w:p')]
    croot = etree.Element(q('w:comments'), nsmap={'w': W})
    for i, (txt, auth) in enumerate(comments):
        if i + 1 >= len(paras): break
        p = paras[i + 1]
        cid = str(i)
        ce = etree.SubElement(croot, q('w:comment'))
        ce.set(q('w:id'), cid); ce.set(q('w:author'), auth)
        cp = etree.SubElement(ce, q('w:p'))
        cr = etree.SubElement(cp, q('w:r'))
        ct = etree.SubElement(cr, q('w:t')); ct.text = txt
        rs = etree.Element(q('w:commentRangeStart')); rs.set(q('w:id'), cid)
        re_ = etree.Element(q('w:commentRangeEnd')); re_.set(q('w:id'), cid)
        ref = etree.Element(q('w:r'))
        etree.SubElement(ref, q('w:commentReference')).set(q('w:id'), cid)
        ppr = p.find(q('w:pPr'))
        if ppr is not None: ppr.addnext(rs)
        else: p.insert(0, rs)
        p.append(re_); p.append(ref)
    items['word/document.xml'] = etree.tostring(root, xml_declaration=True, encoding='UTF-8')
    items['word/comments.xml'] = etree.tostring(croot, xml_declaration=True, encoding='UTF-8')
    ct = etree.fromstring(items['[Content_Types].xml'])
    CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
    o = etree.SubElement(ct, '{%s}Override' % CT)
    o.set('PartName', '/word/comments.xml')
    o.set('ContentType', 'application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
    items['[Content_Types].xml'] = etree.tostring(ct, xml_declaration=True, encoding='UTF-8')
    rels = etree.fromstring(items['word/_rels/document.xml.rels'])
    PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
    r = etree.SubElement(rels, '{%s}Relationship' % PKG)
    r.set('Id', 'rId999'); r.set('Type',
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments')
    r.set('Target', 'comments.xml')
    items['word/_rels/document.xml.rels'] = etree.tostring(rels, xml_declaration=True, encoding='UTF-8')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as out:
        for k, v in items.items(): out.writestr(k, v)

def make_sample_paper():
    from docx import Document
    doc = Document()
    for t in ['毕业论文', '第1章  绪论', '1.1  背景', '正文内容若干字。' * 10,
              '第2章  设计', '2.1  架构', '设计内容若干字。' * 10]:
        doc.add_paragraph(t)
    p = tempfile.mktemp(suffix='.docx')
    doc.save(p)
    return p



# ── 5 正则健壮性（第10章 / [1,2] / 图1） ──
def test_regex_robustness():
    from fact_check import CH_RE, CITE_RE, CAP_RE
    check('章节正则支持两位数', CH_RE.match('第10章总结') is not None,
          str(CH_RE.match('第12章 展望').group(1) if CH_RE.match('第12章 展望') else 'None'))
    check('引用识别 [1,2]', len(CITE_RE.findall('文献[1,2]')) == 1)
    check('引用识别 [1-3]', len(CITE_RE.findall('文献[1-3]')) == 1)
    check('引用识别全角', len(CITE_RE.findall('文献［1］')) == 1)
    check('题注识别 图1', CAP_RE.match('图1 系统架构') is not None)
    check('题注识别 图1.1', CAP_RE.match('图1.1 系统架构') is not None)

# ── 6 唯一片段 + TOC 消歧 ──
def test_unique_snippet():
    from wps_center import unique_snippet
    full = '第5章 系统实现\n正文内容\n第5章 系统实现\n这里是第五章的正文段落内容'
    snip = unique_snippet('这里是第五章的正文段落内容', full)
    check('长段落能取到唯一片段', snip is not None, repr(snip))
    check('唯一片段确实唯一', full.count(snip) == 1)
    short = unique_snippet('第5章 系统实现', full)
    check('短标题识别为不唯一', short is None, repr(short))

# ── 7 批注体检：能查出锚点不一致 ──
def test_audit_detects_broken():
    from audit_comments import audit
    p = make_sample_paper()
    plan = {'author': 'T', 'comments': [{'para': 2, 'text': '正常批注'}]}
    from wps_apply import apply
    apply(p, plan, 'T')
    r = audit(p, 'T')
    check('体检通过正常文件', not r['problems'], str(r['problems']))

    # 人为制造孤儿锚点
    import shutil
    items = {}
    z = zipfile.ZipFile(p)
    for n in z.namelist():
        items[n] = z.read(n)
    z.close()
    d = etree.fromstring(items['word/document.xml'])
    body = d.find(q('w:body'))
    rs = etree.Element(q('w:commentRangeStart')); rs.set(q('w:id'), '999')
    body[1].insert(0, rs)
    items['word/document.xml'] = etree.tostring(d, xml_declaration=True, encoding='UTF-8')
    with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as o:
        for k, v in items.items():
            o.writestr(k, v)
    r2 = audit(p, 'T')
    check('能查出孤儿锚点', any('孤儿' in x for x in r2['problems']), str(r2['problems'])[:70])
    gc.collect()
    os.unlink(p)

# ── 8 AI 痕迹不误伤正常术语 ──
def test_audit_no_false_positive():
    from audit_comments import audit
    p = make_sample_paper()
    plan = {'author': 'T', 'comments': [
        {'para': 2, 'text': '数据模型设计不够细，补字段说明'},
        {'para': 3, 'text': '模型层缺少校验'},
    ]}
    from wps_apply import apply
    apply(p, plan, 'T')
    r = audit(p, 'T')
    check('「数据模型」不误报 AI 痕迹', not r['problems'], str(r['problems'])[:80])
    gc.collect()
    os.unlink(p)

# ── 9 fact_check 不锁文件 ──
def test_no_file_lock():
    from fact_check import analyze, close_analysis
    p = make_sample_paper()
    R, _, _, _ = analyze(p)
    close_analysis(R)
    ok = True
    try:
        os.unlink(p)
    except Exception as e:
        ok = False
        err = str(e)[:50]
    check('close_analysis 后文件可删除', ok, '' if ok else err)

# ── 10 para 定位优先级 ──
def test_para_resolution():
    from wps_center import build_targets
    p = make_sample_paper()
    # 造一个目录+正文重名的场景
    from docx import Document
    doc = Document()
    # 索引: 0=目录 1=第1章(目录) 2=第2章(目录) 3=第1章(正文) 4=正文长段 5=第2章(正文) 6=设计长段
    for s in ['目录', '第1章 绪论', '第2章 设计', '第1章 绪论',
              '正文' * 30, '第2章 设计', '设计内容' * 30]:
        doc.add_paragraph(s)
    doc.save(p)
    issues = [{'para': 3, 'text': 'A'}, {'para': 6, 'text': 'B'}]
    targets, probs = build_targets(p, issues)
    check('para 能解析出目标', len(targets) == 2, str(probs))
    check('重名标题取第2次出现',
          any(t.get('nth', 1) == 2 for t in targets),
          str([(t['para'], t.get('nth')) for t in targets]))
    gc.collect()
    os.unlink(p)

if __name__ == '__main__':
    print("=" * 60)
    print("导师审稿技能 端到端测试")
    print("=" * 60)
    for fn in (test_learn_style, test_fact_check, test_apply, test_backup,
               test_regex_robustness, test_unique_snippet, test_audit_detects_broken,
               test_audit_no_false_positive, test_no_file_lock, test_para_resolution):
        print("\n[%s]" % fn.__name__)
        try:
            fn()
        except Exception as e:
            import traceback
            check(fn.__name__ + ' 异常', False, str(e)[:80])
            traceback.print_exc()
    print()
    print("=" * 60)
    print("通过 %d / 失败 %d" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL: print("  ✗", f)
    sys.exit(0 if not FAIL else 1)