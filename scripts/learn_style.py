# -*- coding: utf-8 -*-
"""learn_style.py - 从历史批注学习批注者风格画像"""
import sys, os, re, json, glob, zipfile, argparse
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s' % (W, t.split(':')[1])

REJECT = ['全改', '重写', '都改', '不合格', '重新写', '全错', '重做', '删掉']
COMPLAIN = ['太少了', '太少', '太碎', '太糊', '太多', '一大段', '太长', '太薄', '看不清', '不行', '不够', '没写', '没有']
REFERENCE = ['看群里', '看群消息', '参考论文', '参考这个', '按最新', '按规范', '按格式']
MINIMAL = ['改', '同上', '图呢', '断表', '单独一页', '太多了', '换位置']
IMPERATIVE_VERBS = ['改', '重写', '补', '删', '加', '换', '拆', '放', '写', '调', '核']
QUESTION = ['？', '?', '吗', '呢', '怎么', '为什么', '哪']

def extract_from_docx(path):
    out = []
    try:
        z = zipfile.ZipFile(path)
        if 'word/comments.xml' not in z.namelist():
            return out
        root = etree.fromstring(z.read('word/comments.xml'))
        for c in root.findall(q('w:comment')):
            txt = ''.join(t.text or '' for t in c.findall('.//' + q('w:t'))).strip()
            if txt:
                out.append({'text': txt, 'author': c.get(q('w:author'), '')})
        z.close()
    except Exception:
        pass
    return out

def extract_from_doc(path):
    import subprocess, tempfile
    PS = '$ErrorActionPreference="SilentlyContinue";$w=New-Object -ComObject Word.Application;$w.Visible=$false;$w.DisplayAlerts=0;$d=$w.Documents.Open($env:DOC,$false,$true);foreach($c in $d.Comments){$t=$c.Range.Text -replace "[`r`n]"," ";if($t.Trim()){Write-Output ($t.Trim())}};$d.Close($false);$w.Quit()'
    f = tempfile.NamedTemporaryFile('w', suffix='.ps1', delete=False, encoding='utf-8-sig')
    f.write(PS); f.close()
    env = dict(os.environ); env['DOC'] = os.path.abspath(path)
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', f.name],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300, env=env)
        return [{'text': l.strip(), 'author': ''} for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return []
    finally:
        os.unlink(f.name)

def extract_all(folder):
    samples = []
    for ext, fn in (('*.docx', extract_from_docx), ('*.doc', extract_from_doc)):
        for p in glob.glob(os.path.join(folder, '**', ext), recursive=True):
            if os.path.basename(p).startswith('~$'):
                continue
            got = fn(p)
            for g in got:
                g['file'] = os.path.basename(p)
            samples.extend(got)
    return samples

def _pct(n, total):
    return round(100.0 * n / total, 1) if total else 0.0

def build_profile(samples, name=''):
    if not samples:
        return {}
    texts = [s['text'] for s in samples]
    lens = sorted(len(t) for t in texts)
    n = len(texts)

    def qtl(p):
        if not lens: return 0
        idx = min(int(len(lens) * p), len(lens) - 1)
        return lens[idx]

    imperative = sum(1 for t in texts if any(v in t for v in IMPERATIVE_VERBS))
    question = sum(1 for t in texts if any(v in t for v in QUESTION))
    declarative = max(0, n - imperative - question)

    def collect(words):
        found = {}
        for t in texts:
            for w in words:
                if w in t:
                    found[w] = found.get(w, 0) + 1
        return sorted(found, key=lambda k: -found[k])[:8]

    exclaim = sum(t.count('！') + t.count('!') for t in texts)
    strength = 1
    if exclaim >= n * 0.3 or imperative / n > 0.7:
        strength = 5
    elif exclaim >= n * 0.1 or imperative / n > 0.5:
        strength = 4
    elif imperative / n > 0.3:
        strength = 3
    elif imperative / n > 0.1:
        strength = 2

    explain = sum(1 for t in texts if any(w in t for w in ('因为', '由于', '否则', '不然')))
    minimal = sum(1 for t in texts if len(t) <= 4)

    return {
        'name': name,
        'samples': n,
        'files': len(set(s.get('file', '') for s in samples)),
        'length': {
            'mean': round(sum(lens) / n, 1),
            'min': lens[0],
            'max': lens[-1],
            'p25': qtl(0.25),
            'p50': qtl(0.50),
            'p90': qtl(0.90),
        },
        'tone': {
            'imperative_pct': _pct(imperative, n),
            'question_pct': _pct(question, n),
            'declarative_pct': _pct(declarative, n),
            'strength': strength,
        },
        'phrases': {
            'reject': collect(REJECT),
            'complain': collect(COMPLAIN),
            'reference': collect(REFERENCE),
            'minimal': collect(MINIMAL),
        },
        'habits': {
            'no_explain': explain / n < 0.2,
            'minimal_pct': _pct(minimal, n),
            'merge_same_para': True,
            'max_per_para': 3,
        },
        'rules': {
            'target_count': '30-35',
            'cover_every_chapter': True,
            'no_stat_phrasing': True,
            'evidence_required': True,
        },
    }

def to_yaml(prof):
    def esc(v):
        if isinstance(v, bool): return 'true' if v else 'false'
        if isinstance(v, (int, float)): return str(v)
        return '"%s"' % str(v).replace('"', '\\"')
    lines = []
    for k, v in prof.items():
        if isinstance(v, dict):
            lines.append('%s:' % k)
            for k2, v2 in v.items():
                if isinstance(v2, dict):
                    lines.append('  %s:' % k2)
                    for k3, v3 in v2.items():
                        lines.append('    %s: %s' % (k3, esc(v3)))
                elif isinstance(v2, list):
                    lines.append('  %s:' % k2)
                    for item in v2:
                        lines.append('    - %s' % esc(item))
                    if not v2:
                        lines.append('    []')
                else:
                    lines.append('  %s: %s' % (k2, esc(v2)))
        else:
            lines.append('%s: %s' % (k, esc(v)))
    return chr(10).join(lines) + chr(10)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', required=True)
    ap.add_argument('--out', default='profile.yaml')
    ap.add_argument('--name', default='')
    a = ap.parse_args()
    print('扫描:', a.samples)
    samples = extract_all(a.samples)
    print('提取批注: %d 条' % len(samples))
    if not samples:
        print('没有找到批注')
        return 1
    prof = build_profile(samples, a.name)
    open(a.out, 'w', encoding='utf-8').write(to_yaml(prof))
    print('画像写入:', a.out)
    print()
    print('样本 %d 条 / %d 篇' % (prof['samples'], prof['files']))
    print('平均 %.1f 字 (%d-%d)' % (prof['length']['mean'], prof['length']['min'], prof['length']['max']))
    print('命令式 %.0f%% 强度 %d/5' % (prof['tone']['imperative_pct'], prof['tone']['strength']))
    print('常用词: %s' % ('、'.join(prof['phrases']['reject'][:4]) or '无'))
    return 0

if __name__ == '__main__':
    sys.exit(main())