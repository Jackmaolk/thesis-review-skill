# -*- coding: utf-8 -*-
"""
fact_check.py —— Phase 0 事实核查（批注前必跑）
输出客观数据，不做判断。没有数据支撑的批注一律不许写。
用法：python fact_check.py paper.docx [rules.yaml]
"""
import sys, os, re, json, zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s' % (W, t.split(':')[1])

def t_of(p):
    return ''.join(t.text or '' for t in p.findall('.//' + q('w:t')))

def norm(t):
    return re.sub(r'[\s\u3000]+', '', t or '')

def analyze(path):
    z = zipfile.ZipFile(path)
    doc = etree.fromstring(z.read('word/document.xml'))
    body = doc.find(q('w:body'))
    blocks = [c for c in body if c.tag in (q('w:p'), q('w:tbl'))]

    paras = []
    for i, b in enumerate(blocks):
        if b.tag == q('w:p'):
            paras.append({'i': i, 'tag': 'p', 'text': t_of(b), 'norm': norm(t_of(b))})
        else:
            paras.append({'i': i, 'tag': 'tbl', 'text': '', 'norm': ''})

    # 正文起点
    c1 = [p['i'] for p in paras if re.match(r'^第1章', p['norm']) and len(p['norm']) < 25]
    body_start = c1[-1] if c1 else 0

    # 章区间
    heads = []
    for p in paras:
        if p['i'] < body_start: continue
        m = re.match(r'^第([1-9])章', p['norm'])
        if m and len(p['norm']) < 25:
            heads.append((int(m.group(1)), p['i']))
    chap = {}
    for k, (no, idx) in enumerate(heads):
        chap[no] = (idx, heads[k+1][1] if k+1 < len(heads) else 10**9)

    R = {'file': os.path.basename(path), 'body_start': body_start,
         '_zip': z,
         'total_blocks': len(blocks), 'paras': paras, 'chapters': chap}

    # ── 1 字数 ──
    def wc(lo, hi):
        return sum(len(p['norm']) for p in paras if lo <= p['i'] < hi and p['tag'] == 'p')

    R['word_count'] = {('ch%d' % no): wc(a, z_) for no, (a, z_) in chap.items()}

    # 摘要
    i_abs = next((p['i'] for p in paras if p['norm'] in ('摘要', '摘　　要')), None)
    i_kw = next((p['i'] for p in paras
                 if p['norm'].startswith('关键词') or p['norm'].startswith('关键字')), None)
    if i_abs and i_kw:
        R['abstract_words'] = wc(i_abs+1, i_kw)
        # 摘要标题后是否空行
        nxt = next((p for p in paras if p['i'] > i_abs and p['tag']=='p'), None)
        R['abstract_blank_after'] = bool(nxt and not nxt['norm'])

    # 结论
    i_conc = next((p['i'] for p in paras if p['norm'] == '结论'), None)
    i_refs = next((p['i'] for p in paras if p['norm'] == '参考文献'), None)
    if i_conc:
        R['conclusion_words'] = wc(i_conc+1, i_refs if i_refs else i_conc+400)

    # ── 2 图表 ──
    CAP = re.compile(r'^(图|表)\s*(\d+[.\-]\d+)')
    figs, tabs = [], []
    for p in paras:
        m = CAP.match(p['norm'])
        if m:
            (figs if m.group(1) == '图' else tabs).append(
                {'para': p['i'], 'no': m.group(2), 'text': p['text'][:40]})
    R['figure_count'] = len(figs)
    R['table_count'] = len(tabs)
    R['figures'] = figs
    R['tables'] = tabs

    # 题注位置：图注前一块是图片段落？
    def prev_has_img(idx):
        for j in range(idx-1, max(idx-4, 0), -1):
            b = blocks[j]
            if b.tag != q('w:p'): return None
            if (b.findall('.//' + q('w:drawing')) or b.findall('.//' + q('w:pict'))
                    or b.findall('.//' + q('w:object'))
                    or b.findall('.//{urn:schemas-microsoft-com:vml}imagedata')):
                return True
            if norm(t_of(b)): return False
        return False
    R['captions_misplaced'] = [f['para'] for f in figs if prev_has_img(f['para']) is False]

    # ── 3 引用标注 ──
    cites = {}
    for no, (a, z_) in chap.items():
        cnt = 0
        for p in paras:
            if a <= p['i'] < z_:
                cnt += len(re.findall(r'\[\d+\]', p['text']))
        cites['ch%d' % no] = cnt
    R['citations'] = cites
    R['citation_total'] = sum(cites.values())

    # ── 4 页眉页码 ──
    sections = []
    for p in paras:
        if p['tag'] != 'p': continue
        idx = blocks[p['i']]
        ppr = idx.find(q('w:pPr'))
        if ppr is None: continue
        sp = ppr.find(q('w:sectPr'))
        if sp is None: continue
        pg = sp.find(q('w:pgNumType'))
        sections.append({'para': p['i'],
                         'fmt': pg.get(q('w:fmt')) if pg is not None else None,
                         'start': pg.get(q('w:start')) if pg is not None else None})
    R['sections'] = sections

    # ── 5 章节分页 ──
    no_page_break = []
    for no, (a, z_) in chap.items():
        idx = blocks[a]
        ppr = idx.find(q('w:pPr'))
        has = ppr is not None and ppr.find(q('w:pageBreakBefore')) is not None
        if not has:
            # 前 3 块有分页符？
            for j in range(max(a-3, 0), a):
                x = etree.tostring(blocks[j]).decode()
                if 'type="page"' in x or 'sectPr' in x: has = True
        if not has: no_page_break.append(no)
    R['chapters_without_break'] = no_page_break

    # ── 6 每条批注候选的验证依据 ──
    return R, blocks, doc, z

if __name__ == '__main__':
    P = sys.argv[1]
    R, _, _, _ = analyze(P)
    out = {k: v for k, v in R.items() if k not in ('paras', 'figures', 'tables', '_zip')}
    print(json.dumps(out, ensure_ascii=False, indent=2))

def close_analysis(R):
    """关闭 analyze 打开的 zip，避免 Windows 文件占用"""
    z = R.get('_zip')
    if z is not None:
        try:
            z.close()
        except Exception:
            pass
        R['_zip'] = None