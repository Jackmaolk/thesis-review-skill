# -*- coding: utf-8 -*-
"""
wps_apply.py —— 按段落索引精确写入批注
用法：python wps_apply.py paper.docx plan.json
plan.json 格式：
{
  "author": "Teacher",
  "comments": [
    {"para": 108, "find": "可选，段内定位", "text": "批注内容"},
    {"chapter": 1, "find": "1.2 国内外研究现状", "text": "..."},
    {"range": "toc", "find": "目    录", "text": "..."}
  ]
}
"""
import sys, os, json, zipfile, re
from lxml import etree
sys.path.insert(0, os.path.dirname(__file__))
from wps_anchor import analyze, q, text_of, norm

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def resolve(info, spec):
    """把 spec 解析成段落索引"""
    if 'para' in spec:
        return spec['para']
    kw = spec.get('find', '')
    rng = spec.get('range')
    if rng == 'toc':
        # 目录范围：正文起点之前
        for p in info['paras']:
            if p['i'] < info['body_start'] and kw in p['norm']:
                return p['i']
        return None
    if rng == 'conclusion':
        return info['conclusion']
    if rng == 'references':
        return info['references']
    chap = spec.get('chapter')
    start = info['chapters'].get(chap, (info['body_start'], 10**9))[0] if chap else info['body_start']
    end = info['chapters'].get(chap, (0, 10**9))[1] if chap else 10**9
    for p in info['paras']:
        if p['i'] < start or p['i'] >= end: continue
        if kw in p['norm']:
            return p['i']
    return None

def apply(path, plan, author="Teacher"):
    info = analyze(path)
    items = info['items']
    doc = info['doc']
    body = doc.find(q('w:body'))
    blocks = [c for c in body if c.tag in (q('w:p'), q('w:tbl'))]

    # 清空旧批注（若无 comments.xml 则新建并注册）
    if 'word/comments.xml' in items:
        croot = etree.fromstring(items['word/comments.xml'])
    else:
        croot = etree.Element(q('w:comments'), nsmap={'w': W})
        # 注册 content-type
        ct = etree.fromstring(items['[Content_Types].xml'])
        CTP = 'http://schemas.openxmlformats.org/package/2006/content-types'
        o = etree.SubElement(ct, '{%s}Override' % CTP)
        o.set('PartName', '/word/comments.xml')
        o.set('ContentType', 'application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
        items['[Content_Types].xml'] = etree.tostring(ct, xml_declaration=True, encoding='UTF-8', standalone=True)
        # 注册关系
        rels = etree.fromstring(items['word/_rels/document.xml.rels'])
        PKGP = 'http://schemas.openxmlformats.org/package/2006/relationships'
        used = {r.get('Id') for r in rels}
        n = 900
        while 'rId%d' % n in used: n += 1
        rel = etree.SubElement(rels, '{%s}Relationship' % PKGP)
        rel.set('Id', 'rId%d' % n)
        rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments')
        rel.set('Target', 'comments.xml')
        items['word/_rels/document.xml.rels'] = etree.tostring(rels, xml_declaration=True, encoding='UTF-8', standalone=True)
    for c in list(croot.findall(q('w:comment'))): croot.remove(c)
    for el in body.findall('.//' + q('w:commentRangeStart')) + body.findall('.//' + q('w:commentRangeEnd')):
        el.getparent().remove(el)
    for el in body.findall('.//' + q('w:commentReference')):
        r = el.getparent(); r.getparent().remove(r)

    W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    ok = miss = 0
    log = []
    for k, spec in enumerate(plan['comments']):
        idx = resolve(info, spec)
        if idx is None:
            miss += 1
            log.append(('MISS', spec.get('find') or str(spec))); continue
        p = blocks[idx]
        if p.tag != q('w:p'):
            miss += 1; log.append(('NOT_P', spec.get('find'))); continue

        cid = str(k)
        # comment 元素
        c = etree.SubElement(croot, q('w:comment'))
        c.set(q('w:id'), cid); c.set(q('w:author'), author)
        c.set(q('w:initials'), author[:1])
        c.set(q('w:date'), '2026-10-27T10:00:00Z')
        cp = etree.SubElement(c, q('w:p'))
        cr = etree.SubElement(cp, q('w:r'))
        ct = etree.SubElement(cr, q('w:t'))
        ct.text = spec['text']
        ct.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

        # 锚点区间
        rs = etree.Element(q('w:commentRangeStart')); rs.set(q('w:id'), cid)
        re_ = etree.Element(q('w:commentRangeEnd')); re_.set(q('w:id'), cid)
        ref = etree.Element(q('w:r'))
        rpr = etree.SubElement(ref, q('w:rPr'))
        etree.SubElement(rpr, q('w:rStyle')).set(q('w:val'), 'CommentReference')
        etree.SubElement(ref, q('w:commentReference')).set(q('w:id'), cid)

        # 放在段落首尾（整段锚定，章节归属明确）
        ppr = p.find(q('w:pPr'))
        if ppr is not None:
            ppr.addnext(rs)
        else:
            p.insert(0, rs)
        p.append(re_); p.append(ref)
        ok += 1
        log.append(('OK', idx, spec['text'][:24]))

    items['word/comments.xml'] = etree.tostring(croot, xml_declaration=True, encoding='UTF-8', standalone=True)
    items['word/document.xml'] = etree.tostring(doc, xml_declaration=True, encoding='UTF-8', standalone=True)
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
        for k2, v in items.items(): out.writestr(k2, v)
    os.replace(tmp, path)
    return ok, miss, log

if __name__ == '__main__':
    path, planf = sys.argv[1], sys.argv[2]
    plan = json.load(open(planf, encoding='utf-8'))
    ok, miss, log = apply(path, plan, plan.get('author', 'Teacher'))
    for l in log: print(l)
    print('OK=%d MISS=%d' % (ok, miss))