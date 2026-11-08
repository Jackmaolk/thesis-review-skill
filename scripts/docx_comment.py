# -*- coding: utf-8 -*-
"""
docx_comment.py —— 向 .docx 写入 Word 原生批注（等价于 审阅->新建批注）
只增加批注，绝不修改正文文字、样式、图片、页眉页脚。
"""
import zipfile, shutil, copy, re, os, datetime
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
PKGREL = 'http://schemas.openxmlformats.org/package/2006/relationships'
COMMENTS_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml'
COMMENTS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'
NS = {'w': W, 'r': R}
def q(tag):
    p, t = tag.split(':')
    return '{%s}%s' % (W if p == 'w' else R, t)

def _text_of_run(run):
    return ''.join(t.text or '' for t in run.findall(q('w:t')))

def _para_runs(p):
    """只取段落直接子级的 w:r，遇到 hyperlink/smartTag 等返回 None 表示结构复杂"""
    runs = []
    for child in p:
        if child.tag == q('w:r'):
            runs.append(child)
        elif child.tag in (q('w:pPr'),):
            continue
        elif child.tag in (q('w:hyperlink'), q('w:smartTag'), q('w:sdt'),
                           q('w:ins'), q('w:del')):
            return None
        elif child.tag in (q('w:bookmarkStart'), q('w:bookmarkEnd'),
                           q('w:commentRangeStart'), q('w:commentRangeEnd'),
                           q('w:proofErr')):
            continue
    return runs

def _split_run(run, cut):
    """在 run 文本的第 cut 个字符处切成两个 run，返回后半个（已插入文档）"""
    txt = _text_of_run(run)
    if cut <= 0 or cut >= len(txt):
        return None
    clone = copy.deepcopy(run)
    for t in clone.findall(q('w:t')):
        clone.remove(t)
    tail = etree.SubElement(clone, q('w:t'))
    tail.text = txt[cut:]
    tail.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    for t in run.findall(q('w:t')):
        t.text = txt[:cut]
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    run.addnext(clone)
    return clone

def _split_at(p, pos):
    """确保段落在字符位置 pos 处是一个 run 边界"""
    runs = _para_runs(p)
    if runs is None:
        return False
    off = 0
    for r in runs:
        t = _text_of_run(r)
        if off < pos < off + len(t):
            _split_run(r, pos - off)
            return True
        off += len(t)
    return False

def _anchor_by_find(p, find):
    """按文字精确定位；返回 (首个run, 末个run) 或 None（定位失败）"""
    runs = _para_runs(p)
    if runs is None:
        return None
    full = ''.join(_text_of_run(r) for r in runs)
    start = full.find(find)
    if start < 0:
        return None
    end = start + len(find)

    # 把 start / end 都变成 run 边界，再重新收集
    _split_at(p, start)
    _split_at(p, end)
    runs = _para_runs(p)
    if runs is None:
        return None

    off = 0
    picked = []
    for r in runs:
        t = _text_of_run(r)
        r_start, r_end = off, off + len(t)
        off = r_end
        if r_end <= start or r_start >= end:
            continue
        picked.append(r)
    if not picked:
        return None
    return (picked[0], picked[-1])

def _new_comment_element(cid, text, author, initials, date):
    c = etree.Element(q('w:comment'))
    c.set(q('w:id'), str(cid))
    c.set(q('w:author'), author)
    c.set(q('w:initials'), initials)
    c.set(q('w:date'), date)
    p = etree.SubElement(c, q('w:p'))
    r = etree.SubElement(p, q('w:r'))
    t = etree.SubElement(r, q('w:t'))
    t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return c

def add_comments(src, dst, comments, author='导师', initials='DS',
                 date=None, dry_run=False):
    """
    comments: [{'para': 段落序号(0基, 与 doc.paragraphs 一致), 'find': 可选精确文字,
                'text': 批注内容, 'severity': 'A'|'B'|'C'}]
    返回 {'ok': n, 'skipped': [...], 'ids': {...}}
    """
    if date is None:
        date = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    shutil.copyfile(src, dst)
    zin = zipfile.ZipFile(src, 'r')
    items = {n: zin.read(n) for n in zin.namelist()}
    zin.close()

    doc = etree.fromstring(items['word/document.xml'])
    body = doc.find(q('w:body'))
    paras = [c for c in body if c.tag == q('w:p')]

    # --- 现有批注 part ---
    if 'word/comments.xml' in items:
        croot = etree.fromstring(items['word/comments.xml'])
        existing = croot.findall(q('w:comment'))
        next_id = max([int(x.get(q('w:id'))) for x in existing] + [0]) + 1
    else:
        croot = etree.Element(q('w:comments'), nsmap={'w': W})
        next_id = 0

    ok, skipped, ids, degraded = 0, [], {}, []
    for c in comments:
        idx = c.get('para')
        if idx is None or idx >= len(paras):
            skipped.append({'para': idx, 'reason': '段落序号越界', 'text': c.get('text','')[:30]})
            continue
        p = paras[idx]
        find = c.get('find')
        if find:
            anchor = _anchor_by_find(p, find)
            if anchor is None:
                anchor = _paragraph_anchor(p)
                if anchor is None:
                    skipped.append({'para': idx, 'reason': '空段落或结构复杂', 'text': c.get('text','')[:30]})
                    continue
                degraded.append({'para': idx, 'find': find})
        else:
            anchor = _paragraph_anchor(p)
            if anchor is None:
                skipped.append({'para': idx, 'reason': '空段落或结构复杂', 'text': c.get('text','')[:30]})
                continue
        first, last = anchor
        cid = next_id
        next_id += 1
        cstart = etree.Element(q('w:commentRangeStart')); cstart.set(q('w:id'), str(cid))
        cend = etree.Element(q('w:commentRangeEnd')); cend.set(q('w:id'), str(cid))
        ref = etree.Element(q('w:r'))
        rpr = etree.SubElement(ref, q('w:rPr'))
        etree.SubElement(rpr, q('w:rStyle')).set(q('w:val'), 'CommentReference')
        cref = etree.SubElement(ref, q('w:commentReference')); cref.set(q('w:id'), str(cid))
        first.addprevious(cstart)
        last.addnext(cref)
        last.addnext(cend)
        croot.append(_new_comment_element(cid, c.get('text',''), author, initials, date))
        ids[cid] = idx
        ok += 1

    items['word/document.xml'] = etree.tostring(doc, xml_declaration=True,
                                                encoding='UTF-8', standalone=True)
    items['word/comments.xml'] = etree.tostring(croot, xml_declaration=True,
                                                encoding='UTF-8', standalone=True)

    # --- 关系 ---
    rels = etree.fromstring(items['word/_rels/document.xml.rels'])
    have = any(r.get('Type') == COMMENTS_REL for r in rels)
    if not have:
        used = {r.get('Id') for r in rels}
        n = 1
        while 'rId%d' % n in used:
            n += 1
        rel = etree.SubElement(rels, '{%s}Relationship' % PKGREL)
        rel.set('Id', 'rId%d' % n)
        rel.set('Type', COMMENTS_REL)
        rel.set('Target', 'comments.xml')
    items['word/_rels/document.xml.rels'] = etree.tostring(
        rels, xml_declaration=True, encoding='UTF-8', standalone=True)

    # --- 内容类型 ---
    ct = etree.fromstring(items['[Content_Types].xml'])
    if not any(o.get('PartName') == '/word/comments.xml' for o in ct):
        o = etree.SubElement(ct, '{%s}Override' % CT)
        o.set('PartName', '/word/comments.xml')
        o.set('ContentType', COMMENTS_TYPE)
    items['[Content_Types].xml'] = etree.tostring(
        ct, xml_declaration=True, encoding='UTF-8', standalone=True)

    if dry_run:
        return {'ok': ok, 'skipped': skipped, 'ids': ids, 'degraded': degraded}

    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in items.items():
            z.writestr(name, data)
    return {'ok': ok, 'skipped': skipped, 'ids': ids}

def _paragraph_anchor(p):
    runs = [r for r in p if r.tag == q('w:r')]
    if not runs:
        return None
    return (runs[0], runs[-1])