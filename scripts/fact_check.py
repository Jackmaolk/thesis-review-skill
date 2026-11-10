# -*- coding: utf-8 -*-
"""
fact_check.py -- Phase 0 事实核查（批注前必跑）
输出客观数据，不做判断。没有数据支撑的批注一律不许写。
用法：python fact_check.py paper.docx
"""
import sys, os, re, json, zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
VML = 'urn:schemas-microsoft-com:vml'
def q(t): return '{%s}%s' % (W, t.split(':')[1])

# 章节标题：支持第1章 ~ 第99章
CH_RE = re.compile(r'^第\s*(\d{1,2})\s*章')
# 引用标注：[1] [1,2] [1-3] [1–3] 以及全角［］
CITE_RE = re.compile(r'[\[［]\s*\d+(?:\s*[,，\-–—~]\s*\d+)*\s*[\]］]')
# 图/表题注：图1.1 图1-1 图1 表2.3
CAP_RE = re.compile(r'^(图|表)\s*(\d+(?:\s*[.\-–]\s*\d+)?)')
# 摘要标题
ABS_KEYS = ('摘要', '中文摘要', 'ABSTRACT', 'Abstract')
# 结论标题
CONC_RE = re.compile(r'^(结论|总结|结语)(与展望|与不足)?$')


def t_of(p):
    return ''.join(t.text or '' for t in p.findall('.//' + q('w:t')))


def norm(t):
    return re.sub(r'[\s\u3000]+', '', t or '')


def has_image(block):
    return bool(block.findall('.//' + q('w:drawing'))
                or block.findall('.//' + q('w:pict'))
                or block.findall('.//' + q('w:object'))
                or block.findall('.//{%s}imagedata' % VML))


def analyze(path):
    z = zipfile.ZipFile(path)
    doc = etree.fromstring(z.read('word/document.xml'))
    body = doc.find(q('w:body'))
    blocks = [c for c in body if c.tag in (q('w:p'), q('w:tbl'))]

    paras = []
    for i, b in enumerate(blocks):
        if b.tag == q('w:p'):
            txt = t_of(b)
            paras.append({'i': i, 'tag': 'p', 'text': txt, 'norm': norm(txt)})
        else:
            paras.append({'i': i, 'tag': 'tbl', 'text': '', 'norm': ''})

    # ── 正文起点：最后一个短「第1章」标题（跳过目录） ──
    c1 = [p['i'] for p in paras
          if CH_RE.match(p['norm']) and p['norm'].startswith('第1章') and len(p['norm']) < 25]
    body_start = c1[-1] if c1 else 0

    # ── 章区间（支持 1-99 章） ──
    heads = []
    for p in paras:
        if p['i'] < body_start:
            continue
        m = CH_RE.match(p['norm'])
        if m and len(p['norm']) < 25:
            heads.append((int(m.group(1)), p['i']))
    chap = {}
    for k, (no, idx) in enumerate(heads):
        chap[no] = (idx, heads[k + 1][1] if k + 1 < len(heads) else len(blocks))

    R = {'file': os.path.basename(path), 'body_start': body_start,
         '_zip': z, 'total_blocks': len(blocks), 'paras': paras, 'chapters': chap}

    # ── 1 图表题注（先算，字数要排除） ──
    figs, tabs = [], []
    cap_idx = set()
    for p in paras:
        m = CAP_RE.match(p['norm'])
        if m:
            cap_idx.add(p['i'])
            item = {'para': p['i'], 'no': norm(m.group(2)), 'text': p['text'][:40]}
            (figs if m.group(1) == '图' else tabs).append(item)
    R['figure_count'] = len(figs)
    R['table_count'] = len(tabs)
    R['figures'] = figs
    R['tables'] = tabs

    # ── 2 字数（排除题注行） ──
    def wc(lo, hi, skip_caps=True):
        return sum(len(p['norm']) for p in paras
                   if lo <= p['i'] < hi and p['tag'] == 'p'
                   and not (skip_caps and p['i'] in cap_idx))

    R['word_count'] = {('ch%d' % no): wc(a, b) for no, (a, b) in chap.items()}

    # ── 3 摘要 ──
    i_abs = next((p['i'] for p in paras
                  if p['norm'] in ABS_KEYS or p['norm'].upper() in ('ABSTRACT',)), None)
    i_kw = next((p['i'] for p in paras
                 if p['norm'].startswith(('关键词', '关键字', 'Key words', 'Keywords'))), None)
    if i_abs is not None and i_kw is not None and i_kw > i_abs:
        R['abstract_words'] = wc(i_abs + 1, i_kw)
        nxt = next((p for p in paras if p['i'] > i_abs and p['tag'] == 'p'), None)
        R['abstract_blank_after'] = bool(nxt and not nxt['norm'])
    else:
        R['abstract_words'] = None
        R['abstract_blank_after'] = None

    # ── 4 结论 ──
    i_conc = next((p['i'] for p in paras
                   if CONC_RE.match(p['norm']) and p['i'] > body_start), None)
    i_refs = next((p['i'] for p in paras
                   if p['norm'] == '参考文献' and p['i'] > body_start), None)
    if i_conc is not None:
        hi = i_refs if (i_refs and i_refs > i_conc) else len(blocks)
        R['conclusion_words'] = wc(i_conc + 1, hi)
    else:
        R['conclusion_words'] = None

    # ── 5 题注位置：图注应在图下方 ──
    def prev_has_img(idx):
        for j in range(idx - 1, max(idx - 4, 0), -1):
            b = blocks[j]
            if b.tag != q('w:p'):
                return None
            if has_image(b):
                return True
            if norm(t_of(b)):
                return False
        return False
    R['captions_misplaced'] = [f['para'] for f in figs if prev_has_img(f['para']) is False]

    # ── 6 引用标注 ──
    cites = {}
    for no, (a, b) in chap.items():
        cnt = 0
        for p in paras:
            if a <= p['i'] < b:
                cnt += len(CITE_RE.findall(p['text']))
        cites['ch%d' % no] = cnt
    R['citations'] = cites
    R['citation_total'] = sum(cites.values())

    # ── 7 分节 / 页码 ──
    sections = []
    for p in paras:
        if p['tag'] != 'p':
            continue
        ppr = blocks[p['i']].find(q('w:pPr'))
        if ppr is None:
            continue
        sp = ppr.find(q('w:sectPr'))
        if sp is None:
            continue
        pg = sp.find(q('w:pgNumType'))
        sections.append({'para': p['i'],
                         'fmt': pg.get(q('w:fmt')) if pg is not None else None,
                         'start': pg.get(q('w:start')) if pg is not None else None})
    R['sections'] = sections

    # ── 8 章前分页 ──
    no_break = []
    for no, (a, b) in chap.items():
        ppr = blocks[a].find(q('w:pPr'))
        has = ppr is not None and ppr.find(q('w:pageBreakBefore')) is not None
        if not has:
            for j in range(max(a - 3, 0), a):
                x = etree.tostring(blocks[j]).decode('utf-8', 'ignore')
                if 'type="page"' in x or 'sectPr' in x:
                    has = True
                    break
        if not has:
            no_break.append(no)
    R['chapters_without_break'] = no_break

    return R, blocks, doc, z


def close_analysis(R):
    """关闭 analyze 打开的 zip，避免 Windows 文件占用"""
    z = R.get('_zip')
    if z is not None:
        try:
            z.close()
        except Exception:
            pass
        R['_zip'] = None


def public_view(R):
    """可 JSON 序列化的视图"""
    skip = ('paras', 'figures', 'tables', '_zip')
    return {k: v for k, v in R.items() if k not in skip}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python fact_check.py paper.docx');
        sys.exit(1)
    R, _, _, z = analyze(sys.argv[1]);
    print(json.dumps(public_view(R), ensure_ascii=False, indent=2));
    close_analysis(R)