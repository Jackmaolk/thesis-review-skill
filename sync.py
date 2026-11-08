# -*- coding: utf-8 -*-
"""sync.py -- 本地技能目录 <-> GitHub 仓库 双向同步

用法：
  python sync.py status    查看差异
  python sync.py push      本地 -> 仓库（本地改完，发布）
  python sync.py pull      仓库 -> 本地（仓库改了，拉回来）
  python sync.py verify    检查脱敏 + 跑测试
"""
import os, sys, subprocess, shutil, filecmp, re

LOCAL = r'E:\deepseekharness\.agents\skills\thesis-review-comments'
REPO  = r'E:\deepseekharness\repo_thesis_review'

# 脱敏映射从本地 .sanitize.json 读取（该文件不进仓库）
def load_sanitize():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sanitize.json')
    if not os.path.exists(p):
        return {}
    import json
    with open(p, encoding='utf-8') as f:
        return json.load(f)

SANITIZE = load_sanitize()

# 同步哪些文件
PATTERNS = ['*.md', '*.yaml', '*.py']
SKIP_DIRS = {'__pycache__', '.git', 'docs'}

def walk(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(('.md', '.yaml', '.py')):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            out.append(rel)
    return sorted(out)

def sanitize_text(t):
    for k, v in SANITIZE.items():
        t = t.replace(k, v)
    return t

def cmd_status():
    lf, rf = set(walk(LOCAL)), set(walk(REPO))
    print('本地独有:', sorted(lf - rf) or '无')
    print('仓库独有:', sorted(rf - lf) or '无')
    print()
    diff = []
    for rel in sorted(lf & rf):
        a = os.path.join(LOCAL, rel)
        b = os.path.join(REPO, rel)
        with open(a, encoding='utf-8') as f: ca = f.read()
        with open(b, encoding='utf-8') as f: cb = f.read()
        if sanitize_text(ca) != cb:
            diff.append(rel)
    if diff:
        print('内容有差异（本地脱敏后 != 仓库）:')
        for d in diff: print('  -', d)
    else:
        print('内容一致（本地脱敏后 == 仓库）')
    return 0

def cmd_push():
    n = 0
    for rel in walk(LOCAL):
        a = os.path.join(LOCAL, rel)
        b = os.path.join(REPO, rel)
        os.makedirs(os.path.dirname(b), exist_ok=True)
        with open(a, encoding='utf-8') as f:
            content = sanitize_text(f.read())
        old = None
        if os.path.exists(b):
            with open(b, encoding='utf-8') as f: old = f.read()
        if old != content:
            with open(b, 'w', encoding='utf-8') as f:
                f.write(content)
            print('  更新', rel)
            n += 1
    print('推送 %d 个文件到仓库目录' % n)
    return 0 if n >= 0 else 1

def cmd_pull():
    n = 0
    for rel in walk(REPO):
        a = os.path.join(REPO, rel)
        b = os.path.join(LOCAL, rel)
        if not os.path.exists(b):
            print('  仓库新增', rel, '（本地没有，跳过以免覆盖）')
            continue
        with open(a, encoding='utf-8') as f: ca = f.read()
        with open(b, encoding='utf-8') as f: cb = f.read()
        if ca != sanitize_text(cb):
            print('  差异', rel, '（需人工确认，脚本不动）')
            n += 1
    if n == 0:
        print('仓库没有比本地更新的内容')
    return 0

def cmd_verify():
    print('=== 脱敏检查 ===')
    bad = 0
    for rel in walk(REPO):
        p = os.path.join(REPO, rel)
        with open(p, encoding='utf-8', errors='ignore') as f:
            c = f.read()
        for k in SANITIZE:
            if k in c:
                print('  泄露:', rel, '<-', k)
                bad += 1
    print('  干净' if bad == 0 else '  发现 %d 处' % bad)
    print()
    print('=== 跑测试 ===')
    env = dict(os.environ); env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run([sys.executable, os.path.join(REPO, 'tests', 'test_pipeline.py')],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    tail = [l for l in r.stdout.splitlines() if '通过' in l or '失败' in l]
    print('  ' + (tail[-1] if tail else '无输出'))
    return 0 if bad == 0 and r.returncode == 0 else 1

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    fn = {'status': cmd_status, 'push': cmd_push, 'pull': cmd_pull, 'verify': cmd_verify}.get(cmd)
    if not fn:
        print(__doc__)
        sys.exit(1)
    sys.exit(fn())