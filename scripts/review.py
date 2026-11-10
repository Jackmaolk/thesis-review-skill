# -*- coding: utf-8 -*-
"""
review.py -- 一条命令跑完整流程

用法：
  python review.py plan.json                # 备份 -> 核查 -> 写批注 -> 体检
  python review.py plan.json --dry-run      # 只验证定位，不写
  python review.py plan.json --check-only   # 只做备份+核查+体检

plan.json 见 wps_center.py 说明。
"""
import sys, os, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from backup import backup, verify
from fact_check import analyze, close_analysis, public_view
from audit_comments import audit


def step(n, title):
    print()
    print('=' * 56)
    print('%s %s' % (n, title))
    print('=' * 56)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not args:
        print(__doc__)
        return 1

    cfg = json.load(open(args[0], encoding='utf-8'))
    docx = cfg.get('docx')
    if not docx or not os.path.exists(docx):
        print('文档不存在:', docx)
        return 1
    author = cfg.get('author') or ''
    if not author:
        print('错误: plan.json 必须提供 author')
        return 1

    # 1 备份
    step('1/4', '备份 + 完整性校验')
    dst, h, ok, msg = backup(docx, 'review')
    print('  备份:', os.path.basename(dst))
    print('  SHA :', h)
    print('  校验:', ('OK ' if ok else 'FAIL ') + msg)
    if not ok:
        return 1

    # 2 事实核查
    step('2/4', '事实核查（客观数据）')
    R, _, _, _ = analyze(docx)
    v = public_view(R)
    close_analysis(R)
    for k in ('body_start', 'abstract_words', 'conclusion_words',
              'figure_count', 'table_count', 'citation_total'):
        print('  %-18s %s' % (k, v.get(k)))
    print('  word_count        %s' % v.get('word_count'))
    print('  citations         %s' % v.get('citations'))
    if v.get('chapters_without_break'):
        print('  章前缺分页        %s' % v['chapters_without_break'])
    if v.get('captions_misplaced'):
        print('  图注位置异常      %s' % v['captions_misplaced'])

    if '--check-only' in flags:
        step('3/4', '跳过写入（--check-only）')
    else:
        # 3 写批注
        step('3/4', '写入批注')
        cmd = [sys.executable, os.path.join(HERE, 'wps_center.py'), args[0]]
        if '--dry-run' in flags:
            cmd.append('--dry-run')
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        print(r.stdout.strip())
        if r.stderr.strip():
            print('STDERR:', r.stderr.strip()[-300:])
        if r.returncode != 0:
            print('  写入未全部成功，继续体检')

    # 4 体检
    step('4/4', '批注体检')
    rep = audit(docx, author)
    print('  批注数  =', rep['comments'])
    if rep.get('anchors'):
        a = rep['anchors']
        print('  锚点    = start %d / end %d / ref %d'
              % (a['start'], a['end'], a['reference']))
    print('  作者    =', rep['authors'] or '无')
    if rep.get('length'):
        L = rep['length']
        print('  长度    = 平均 %.1f 字 (%d-%d)' % (L['mean'], L['min'], L['max']))
    print('  问题    =', rep['problems'] or 'none')
    for w in rep['warnings']:
        print('  提醒    =', w)

    return 0 if not rep['problems'] else 1


if __name__ == '__main__':
    sys.exit(main())