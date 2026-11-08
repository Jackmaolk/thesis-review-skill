# -*- coding: utf-8 -*-
"""publish.py -- 一键发布：同步 -> 脱敏检查 -> 测试 -> 提交 -> 推送

用法：
  python publish.py "更新说明"
"""
import os, sys, subprocess

REPO = os.path.dirname(os.path.abspath(__file__))

def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd or REPO, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', shell=isinstance(cmd, str))
    if r.stdout.strip(): print(r.stdout.strip())
    if r.stderr.strip() and r.returncode != 0:
        print('ERR:', r.stderr.strip()[:300])
    if check and r.returncode != 0:
        print('失败，停止')
        sys.exit(1)
    return r

def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else '更新技能'
    py = sys.executable

    print('=' * 50)
    print('1/5 同步本地 -> 仓库')
    print('=' * 50)
    run([py, os.path.join(REPO, 'sync.py'), 'push'])

    print()
    print('=' * 50)
    print('2/5 脱敏检查 + 测试')
    print('=' * 50)
    run([py, os.path.join(REPO, 'sync.py'), 'verify'])

    print()
    print('=' * 50)
    print('3/5 提交')
    print('=' * 50)
    run(['git', 'add', '-A'])
    r = run(['git', 'status', '--porcelain'], check=False)
    if not r.stdout.strip():
        print('没有变化，不需要提交')
        return 0
    run(['git', '-c', 'user.name=Jackmaolk', '-c', 'user.email=mismaolk@gmail.com',
         'commit', '-m', msg])

    print()
    print('=' * 50)
    print('4/5 推送 GitHub')
    print('=' * 50)
    run(['git', 'push', 'origin', 'master'])

    print()
    print('=' * 50)
    print('5/5 完成')
    print('=' * 50)
    run(['git', 'log', '--oneline', '-1'])
    print()
    print('仓库: https://github.com/Jackmaolk/thesis-review-skill')
    return 0

if __name__ == '__main__':
    sys.exit(main())