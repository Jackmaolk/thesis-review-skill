# -*- coding: utf-8 -*-
"""
wps_anchor.py —— 精确锚定批注（跳过目录，章内不越界）
用段落索引直接锚定，不依赖 Find 的全文搜索。
"""
import zipfile, re, json, os, sys

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s' % (W, t.split(':')[1])

def text_of(p):
    return ''.join(t.text or '' for t in p.findall('.//' + q('w:t')))

def norm(t):
    return re.sub(r'[\s\u3000]+', '', t or '')

def load(path):
    z = zipfile.ZipFile(path)
    items = {n: z.read(n) for n in z.namelist()}
    z.close()
    doc = etree_from(items['word/document.xml'])
    return items, doc

def etree_from(data):
    from lxml import etree
    return etree.fromstring(data)

def analyze(path):
    from lxml import etree
    items, doc = load(path)
    body = doc.find(q('w:body'))
    blocks = [c for c in body if c.tag in (q('w:p'), q('w:tbl'))]
    paras = []
    for i, b in enumerate(blocks):
        if b.tag == q('w:p'):
            t = text_of(b)
            paras.append({'i': i, 'text': t, 'norm': norm(t)})

    # 正文起点：最后一个短「第1章」= 真正的绪论（前面那个在目录里）
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

    # 特殊区块
    def first_after(pred, start=body_start):
        for p in paras:
            if p['i'] >= start and pred(p['norm']):
                return p['i']
        return None

    conc = first_after(lambda n: n == '结论') or first_after(lambda n: n.startswith('结论'))
    refs = first_after(lambda n: n == '参考文献')
    return {
        'items': items, 'doc': doc,
        'paras': paras, 'body_start': body_start,
        'chapters': chap, 'conclusion': conc, 'references': refs,
    }

def find_para(info, keyword, *, chapter=None, after=None, before=None, exact=False):
    """在指定范围内找第一个含 keyword 的段落，返回段索引"""
    lo = info['body_start']
    hi = 10**9
    if chapter is not None:
        r = info['chapters'].get(chapter)
        if not r: return None
        lo, hi = r
    if after is not None: lo = max(lo, after)
    if before is not None: hi = min(hi, before)
    for p in info['paras']:
        if p['i'] < lo or p['i'] >= hi: continue
        if (p['norm'] == keyword) if exact else (keyword in p['norm']):
            return p['i']
    return None

if __name__ == '__main__':
    P = sys.argv[1]
    info = analyze(P)
    print("正文起点段:", info['body_start'])
    print("章区间:", {k: v for k, v in sorted(info['chapters'].items())})
    print("结论段:", info['conclusion'], " 参考文献段:", info['references'])
