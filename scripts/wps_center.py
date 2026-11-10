# -*- coding: utf-8 -*-
"""
wps_center.py -- 逐条写入批注，目标滚动到屏幕垂直居中

用法：
  python wps_center.py plan.json              # 正常写入
  python wps_center.py plan.json --dry-run    # 只检查定位，不写入

plan.json：
  {
    "docx": "论文.docx",
    "author": "老师姓名",
    "delay": 2000,
    "center": 9,
    "issues": [
      {"para": 114, "text": "批注内容"},      // 推荐：段落索引
      {"find": "唯一文本", "text": "批注内容"}  // 兼容：文本定位
    ]
  }

定位原理：
  用 para 拿到段落全文，再算一个「全文唯一」的短片段，用该片段定位。
  避免短标题（如「第5章 系统实现」）在目录和正文各出现一次而锚错位置。
"""
import sys, os, json, subprocess, tempfile, base64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fact_check import analyze, close_analysis


def unique_snippet(text, full, min_len=8):
    """从 text 里找一个在 full 中只出现一次的短片段；找不到返回 None"""
    t = (text or '').strip()
    if not t:
        return None
    if len(t) <= min_len:
        return t if full.count(t) == 1 else None
    # 窗口从短到长，上限为整段长度
    for n in range(min_len, len(t) + 1):
        for start in range(0, len(t) - n + 1):
            piece = t[start:start + n]
            if piece.strip() and full.count(piece) == 1:
                return piece
    return None


def build_targets(docx, issues):
    """把 plan 里的 para/find 统一解析成可定位的 snippet + 第几次出现"""
    R, _, _, _ = analyze(docx)
    pmap = {p['i']: p['text'] for p in R['paras']}
    full = '\n'.join(p['text'] for p in R['paras'])
    body_start = R.get('body_start', 0)
    # 每段之前的所有文本，用于精确算「第几次出现」
    prefix = {}
    acc = []
    for p in R['paras']:
        prefix[p['i']] = '\n'.join(acc)
        acc.append(p['text'])
    pre_body = '\n'.join(p['text'] for p in R['paras'] if p['i'] < body_start)
    close_analysis(R)

    out, problems = [], []
    for n, it in enumerate(issues, 1):
        text = it.get('text', '')
        if 'para' in it:
            para = it['para']
            src = pmap.get(para, '')
            if not src.strip():
                problems.append('#%d para=%s 是空段落，跳过' % (n, para));
                continue
            snip = unique_snippet(src, full)
            if not snip:
                # 重复段落：用整段（最多 60 字）作片段，靠 nth 精确定位
                snip = src.strip()[:60]
                problems.append('#%d para=%s 段落内容重复，用 nth 定位（第 %d 次）'
                                % (n, para, 0))
            nth = prefix.get(para, '').count(snip) + 1
            out.append({'find': snip, 'text': text, 'para': para,
                        'nth': nth, 'origin': src[:40]})
        elif 'find' in it:
            f = it['find']
            cnt = full.count(f)
            if cnt == 0:
                problems.append('#%d find=%r 在文档里找不到' % (n, f[:20]));
                continue
            nth = pre_body.count(f) + 1
            if cnt > 1:
                problems.append('#%d find=%r 全文出现 %d 次，将取正文第 %d 次' % (n, f[:20], cnt, nth));
            out.append({'find': f, 'text': text, 'para': None,
                        'nth': nth, 'origin': f[:40]})
        else:
            problems.append('#%d 缺少 para 或 find' % n)
    return out, problems


PS_TMPL = r'''$ErrorActionPreference = "Continue"
$payload = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("__B64__")) | ConvertFrom-Json
$docPath = "__DOCX__"
$author  = "__AUTHOR__"
$delay   = __DELAY__
$center  = __CENTER__
$dryRun  = __DRYRUN__

$sig = @"
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
"@
Add-Type -MemberDefinition $sig -Name WC -Namespace SWC

$k = $null
try { $k = [Runtime.InteropServices.Marshal]::GetActiveObject("KWps.Application") } catch {}
if ($k -eq $null) { $k = New-Object -ComObject KWps.Application }
$k.Visible = $true
$k.DisplayAlerts = 0
if ($author) { try { $k.UserName = $author } catch {} }

$d = $null
try { foreach ($doc in $k.Documents) { if ($doc.FullName -eq $docPath) { $d = $doc } } } catch {}
if ($d -eq $null) { $d = $k.Documents.Open($docPath) }

foreach ($p in Get-Process) {
  if ($p.MainWindowHandle -ne 0 -and $p.ProcessName -notmatch "^(wps|explorer)$") {
    [SWC.WC]::ShowWindow($p.MainWindowHandle, 6) | Out-Null
  }
}
Start-Sleep -Milliseconds 800
foreach ($p in Get-Process wps) {
  if ($p.MainWindowHandle -ne 0) {
    [SWC.WC]::ShowWindow($p.MainWindowHandle, 3) | Out-Null
    [SWC.WC]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
  }
}
Start-Sleep -Milliseconds 1500
$d.ActiveWindow.View.ShowComments = $true

$n = 0; $miss = 0; $bad = 0
foreach ($it in $payload) {
  $rng = $d.Content
  $f = $rng.Find
  $f.ClearFormatting()
  $f.Text = $it.find
  $f.Forward = $true
  $f.Wrap = 0
  $hit = $false
  $nth = 1
  if ($it.nth) { $nth = [int]$it.nth }
  for ($k = 0; $k -lt $nth; $k++) {
    if ($f.Execute()) {
      $hit = $true
      if ($k -lt $nth - 1) { $rng.Collapse(0) | Out-Null }
    } else { $hit = $false; break }
  }
  if ($hit) {
    $found = $rng.Text
    if ($found -notlike "*" + $it.find + "*") {
      $bad++
      Write-Output ("WRONG " + $it.find + " 实际命中: " + $found.Substring(0, [Math]::Min(30, $found.Length)))
      continue
    }
    if (-not $dryRun) { $d.Comments.Add($rng, $it.text) | Out-Null }
    $n++
    try {
      $d.ActiveWindow.ScrollIntoView($rng)
      Start-Sleep -Milliseconds 300
      if ($center -gt 0) { $d.ActiveWindow.SmallScroll(0, -$center, 0, 0) }
    } catch {}
    if (-not $dryRun) { Start-Sleep -Milliseconds $delay }
    Write-Output ("[" + $n + "] " + $it.find)
  } else {
    $miss++
    Write-Output ("MISS " + $it.find)
  }
}
if (-not $dryRun) { $d.Save() }
Write-Output ("TOTAL=" + $d.Comments.Count + " OK=" + $n + " MISS=" + $miss + " WRONG=" + $bad)
'''


def run(docx, targets, author, delay=2000, center=9, dry_run=False):
    b64 = base64.b64encode(json.dumps(targets, ensure_ascii=False).encode('utf-8')).decode()
    ps = (PS_TMPL
          .replace('__B64__', b64)
          .replace('__DOCX__', docx.replace('\\', '\\\\'))
          .replace('__AUTHOR__', author or '')
          .replace('__DELAY__', str(int(delay)))
          .replace('__CENTER__', str(int(center)))
          .replace('__DRYRUN__', '$true' if dry_run else '$false'))
    fd, path = tempfile.mkstemp(suffix='.ps1')
    os.close(fd)
    with open(path, 'w', encoding='utf-8-sig') as f:
        f.write(ps)
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                            '-File', path], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=3600)
        return r.stdout, r.stderr
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not args:
        print(__doc__)
        return 1
    cfg = json.load(open(args[0], encoding='utf-8'))
    dry = '--dry-run' in flags

    docx = cfg.get('docx')
    if not docx or not os.path.exists(docx):
        print('文档不存在:', docx)
        return 1
    author = cfg.get('author') or ''
    if not author:
        print('错误: plan.json 必须提供 author（批注显示的名字）')
        return 1

    targets, problems = build_targets(docx, cfg.get('issues', []))
    print('待写入: %d 条' % len(targets))
    if problems:
        print('定位问题 %d 条:' % len(problems))
        for p in problems:
            print('  !', p)
    if dry:
        print('--- DRY RUN：只验证定位，不写入 ---')
        for i, t in enumerate(targets, 1):
            print('  [%d] 第%d次 %-26r <- %s' % (i, t.get('nth',1), t['find'][:24], t['origin'][:30]))
        print()
        out, err = run(docx, targets, author, 0, cfg.get('center', 9), True)
        print(out.strip())
        if err.strip():
            print('STDERR:', err.strip()[-300:])
        return 0 if ('MISS=0' in out and 'WRONG=0' in out) else 1

    out, err = run(docx, targets, author, cfg.get('delay', 2000),
                   cfg.get('center', 9), dry)
    print(out.strip())
    if err.strip():
        print('STDERR:', err.strip()[-400:])
    return 0 if 'MISS=0' in out and 'WRONG=0' in out else 1


if __name__ == '__main__':
    sys.exit(main())