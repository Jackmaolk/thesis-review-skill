# -*- coding: utf-8 -*-
"""
audit_comments.py -- 批注体检（写完必跑）

检查项：
  1. comments.xml 批注数 == document.xml 的 start/end/reference 三处锚点数
  2. 有没有锚在空段落上
  3. 批注作者是否统一
  4. 有没有 AI 痕迹词

用法：
  python audit_comments.py 论文.docx [期望作者]
"""
import sys, os, re, zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s' % (W, t.split(':')[1])

# AI 痕迹词：只查明确带 AI 属性的，避免误伤正常术语（如「数据模型」）
BANNED = ['AI预审', 'AI审核', '智能生成', '大模型生成', 'ChatGPT', 'GPT-4', 'Claude',
          '人工智能生成', '机器生成', '自动生成批注']


def audit(path, expect_author=None):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    res = {'comments': 0, 'authors': [], 'problems': [], 'warnings': []}

    if 'word/comments.xml' not in names:
        res['problems'].append('没有 word/comments.xml（文件里没有批注）')
        z.close()
        return res

    croot = etree.fromstring(z.read('word/comments.xml'))
    droot = etree.fromstring(z.read('word/document.xml'))
    z.close()

    # 1 数量一致
    cmts = croot.findall(q('w:comment'))
    res['comments'] = len(cmts)
    n_start = len(droot.findall('.//' + q('w:commentRangeStart')))
    n_end = len(droot.findall('.//' + q('w:commentRangeEnd')))
    n_ref = len(droot.findall('.//' + q('w:commentReference')))
    res['anchors'] = {'start': n_start, 'end': n_end, 'reference': n_ref}
    if not (res['comments'] == n_start == n_end == n_ref):
        res['problems'].append(
            '锚点不一致：批注 %d / start %d / end %d / ref %d'
            % (res['comments'], n_start, n_end, n_ref))

    # 2 id 对得上（孤儿锚点 / 野批注）
    cids = {c.get(q('w:id')) for c in cmts}
    aids = {e.get(q('w:id')) for e in droot.findall('.//' + q('w:commentRangeStart'))}
    orphan = aids - cids
    naked = cids - aids
    if orphan:
        res['problems'].append('孤儿锚点 %d 个（有 start 没有对应批注）: %s'
                               % (len(orphan), sorted(orphan)[:5]))
    if naked:
        res['problems'].append('野批注 %d 个（有批注没有 start 锚点）: %s'
                               % (len(naked), sorted(naked)[:5]))

    # 3 作者
    authors = sorted({c.get(q('w:author')) or '' for c in cmts})
    res['authors'] = authors
    if expect_author and authors and authors != [expect_author]:
        res['problems'].append('作者不一致：期望 %r，实际 %r' % (expect_author, authors))
    if any(not a for a in authors):
        res['problems'].append('有批注作者为空')

    # 4 空段落锚点
    body = droot.find(q('w:body'))
    blocks = [c for c in body if c.tag == q('w:p')] if body is not None else []
    empty = 0
    for b in blocks:
        if not b.findall('.//' + q('w:commentRangeStart')):
            continue
        txt = ''.join(t.text or '' for t in b.findall('.//' + q('w:t')))
        if not txt.strip():
            empty += 1
    if empty:
        res['problems'].append('锚在空段落上的批注 %d 个' % empty)

    # 5 AI 痕迹
    for c in cmts:
        txt = ''.join(t.text or '' for t in c.findall('.//' + q('w:t')))
        low = txt.lower()
        for b in BANNED:
            if b.lower() in low:
                res['problems'].append('AI 痕迹 %r: %s' % (b, txt[:40]))
                break

    # 6 长度提醒（不算错误）
    lens = [len(''.join(t.text or '' for t in c.findall('.//' + q('w:t')))) for c in cmts]
    if lens:
        avg = sum(lens) / len(lens)
        res['length'] = {'mean': round(avg, 1), 'min': min(lens), 'max': max(lens)}
        if avg > 60:
            res['warnings'].append('批注平均 %.0f 字，偏长，可能不像真人语气' % avg)

    return res


def report(path, expect_author=None):
    r = audit(path, expect_author)
    print('文件      =', os.path.basename(path))
    print('批注数    =', r['comments'])
    if r.get('anchors'):
        a = r['anchors']
        print('锚点      = start %d / end %d / ref %d' % (a['start'], a['end'], a['reference']))
    print('作者      =', r['authors'] or '无')
    if r.get('length'):
        L = r['length']
        print('长度      = 平均 %.1f 字 (%d-%d)' % (L['mean'], L['min'], L['max']))
    if r['problems']:
        print('问题      =')
        for p in r['problems']:
            print('   x', p)
    else:
        print('问题      = none')
    if r['warnings']:
        for w in r['warnings']:
            print('   ! ', w)
    return 0 if not r['problems'] else 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    who = sys.argv[2] if len(sys.argv) > 2 else None
    sys.exit(report(sys.argv[1], who))