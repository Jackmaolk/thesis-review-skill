# -*- coding: utf-8 -*-
"""format_check.py —— 论文格式审查（解析样式继承，降低误报）"""
import zipfile, re, json, sys
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s' % (W, t.split(':')[1])
FW = '\u3000'

def norm(t):
    return re.sub(r'[\s' + FW + r']+', '', t or '')

def _on(el):
    if el is None: return None
    v = el.get(q('w:val'))
    return not (v is not None and v in ('0', 'false', 'off'))

class Styles:
    def __init__(self, z):
        self.byid = {}
        self.defrpr = None
        try:
            root = etree.fromstring(z.read('word/styles.xml'))
        except KeyError:
            return
        dd = root.find(q('w:docDefaults'))
        if dd is not None:
            rp = dd.find(q('w:rPrDefault'))
            if rp is not None:
                self.defrpr = rp.find(q('w:rPr'))
        for st in root.findall(q('w:style')):
            sid = st.get(q('w:styleId'))
            based = st.find(q('w:basedOn'))
            nm = st.find(q('w:name'))
            self.byid[sid] = {
                'based': based.get(q('w:val')) if based is not None else None,
                'rpr': st.find(q('w:rPr')),
                'name': nm.get(q('w:val')) if nm is not None else sid,
            }

    def chain(self, sid):
        out, seen = [], set()
        while sid and sid not in seen and sid in self.byid:
            seen.add(sid)
            out.append(self.byid[sid])
            sid = self.byid[sid]['based']
        return out

    def rpr_of(self, p):
        merged = {}
        if self.defrpr is not None:
            for c in self.defrpr:
                merged[c.tag] = c
        ppr = p.find(q('w:pPr'))
        sid = None
        if ppr is not None and ppr.find(q('w:pStyle')) is not None:
            sid = ppr.find(q('w:pStyle')).get(q('w:val'))
        for st in reversed(self.chain(sid)):
            if st['rpr'] is not None:
                for c in st['rpr']:
                    merged[c.tag] = c
        first = p.find(q('w:r'))
        if first is not None:
            direct = first.find(q('w:rPr'))
            if direct is not None:
                for c in direct:
                    merged[c.tag] = c
        return merged

    def fonts(self, p):
        """返回 (中文字体, 西文字体)"""
        f = self.rpr_of(p).get(q('w:rFonts'))
        if f is None: return (None, None)
        return (f.get(q('w:eastAsia')), f.get(q('w:ascii')))

    def font(self, p):
        ea, ascii_ = self.fonts(p)
        txt = para_text(p)
        cjk = len(re.findall(r'[\u4e00-\u9fff]', txt))
        total = len(re.sub(r'\s', '', txt))
        if total == 0: return ea or ascii_
        # 中文占主导就看中文字体，否则看西文字体
        return ea if cjk * 2 >= total else (ascii_ or ea)

    def size(self, p):
        e = self.rpr_of(p).get(q('w:sz'))
        return round(int(e.get(q('w:val'))) / 2, 1) if e is not None else None

    def bold(self, p):
        return bool(_on(self.rpr_of(p).get(q('w:b'))))

    def indent(self, p):
        ppr = p.find(q('w:pPr'))
        if ppr is None: return None
        i = ppr.find(q('w:ind'))
        return i.get(q('w:firstLine')) if i is not None else None

def para_text(p):
    return ''.join(t.text or '' for t in p.findall('.//' + q('w:t')))

H1 = re.compile(r'^第[一二三四五六七八九十0-9]+章')
H2 = re.compile(r'^\d+\.\d+[^.\d]')
H3 = re.compile(r'^\d+\.\d+\.\d+')
CAP = re.compile(r'^(图|表)\s*\d+[.\-–—]\s*\d+')

def classify(t, style_name=''):
    n = norm(t)
    if not n: return 'blank'
    sn = (style_name or '').lower()
    if 'toc' in sn: return 'toc'
    if n in ('摘要', 'ABSTRACT', 'Abstract'): return 'abshead'
    if n.startswith('关键词') or n.lower().startswith('keywords'): return 'keywords'
    if n == '目录': return 'tochead'
    if n in ('结论', '参考文献', '致谢', '附录'): return 'special'
    s = t.strip()
    if H3.match(s): return 'h3'
    if H2.match(s): return 'h2'
    if H1.match(s) and len(n) <= 30 and not re.search(r'[，。；,;]', s): return 'h1'
    if CAP.match(s): return 'caption'
    return 'body'

def check(path, rules):
    z = zipfile.ZipFile(path)
    root = etree.fromstring(z.read('word/document.xml'))
    styles = Styles(z)
    body = root.find(q('w:body'))
    raw = [p for p in body if p.tag == q('w:p')]

    items = []
    for i, p in enumerate(raw):
        ppr = p.find(q('w:pPr'))
        sid = None
        if ppr is not None and ppr.find(q('w:pStyle')) is not None:
            sid = ppr.find(q('w:pStyle')).get(q('w:val'))
        sname = styles.byid.get(sid, {}).get('name', sid or '')
        t = para_text(p)
        items.append({'idx': i, 'text': t, 'kind': classify(t, sname), 'style': sname,
                      'font': styles.font(p), 'size': styles.size(p),
                      'bold': styles.bold(p), 'indent': styles.indent(p)})

    abs_i = next((k['idx'] for k in items if k['kind'] == 'abshead'), None)
    toc_i = next((k['idx'] for k in items if k['kind'] == 'tochead'), None)
    h1s = [k['idx'] for k in items if k['kind'] == 'h1']
    body_start = h1s[len(h1s)//2] if h1s else 0

    kinds = rules.get('kinds', {})
    issues, in_ref = [], False
    for k in items:
        i, t, kind = k['idx'], k['text'], k['kind']
        if abs_i is not None and i < abs_i: continue
        if toc_i is not None and toc_i <= i < body_start: continue
        if kind in ('blank', 'toc', 'tochead'): continue
        if kind == 'special':
            if norm(t) == '参考文献': in_ref = True
            continue
        if in_ref: kind = 'ref'
        spec = kinds.get(kind)
        if not spec: continue
        find = t.strip()[:20]

        if spec.get('font') and k['font'] and k['font'] != spec['font']:
            issues.append({'para': i, 'find': find, 'type': 'font',
                'actual': k['font'], 'expect': spec['font'],
                'text': '本段字体是%s，%s要用%s，改一下。' % (k['font'], spec.get('name',''), spec['font'])})
        if spec.get('size') and k['size'] and abs(k['size'] - spec['size']) > 0.05:
            issues.append({'para': i, 'find': find, 'type': 'size',
                'actual': k['size'], 'expect': spec['size'],
                'text': '这里是%s磅，%s要用%s磅，调过来。' % (k['size'], spec.get('name',''), spec['size'])})
        if spec.get('bold') is not None and k['bold'] != spec['bold']:
            issues.append({'para': i, 'find': find, 'type': 'bold',
                'actual': k['bold'], 'expect': spec['bold'],
                'text': '%s这里%s加粗，改掉。' % (spec.get('name',''), '多' if k['bold'] else '没')})
        if kind == 'body' and spec.get('firstLine'):
            fl, want = k['indent'], int(spec['firstLine'])
            if fl is None or abs(int(fl) - want) > 40:
                issues.append({'para': i, 'find': find, 'type': 'indent',
                    'actual': fl or 0, 'expect': want,
                    'text': '首行缩进不对，这里是%s，正文要2字符。' % (fl or '无缩进')})
    return items, issues

if __name__ == '__main__':
    import yaml
    rules = yaml.safe_load(open(sys.argv[2], encoding='utf-8'))
    items, issues = check(sys.argv[1], rules)
    cnt = {}
    for i in issues: cnt[i['type']] = cnt.get(i['type'], 0) + 1
    print(json.dumps({'total_para': len(items), 'total_issue': len(issues),
                      'by_type': cnt, 'issues': issues}, ensure_ascii=False, indent=1))