# -*- coding: utf-8 -*-
"""
wps_center.py —— 逐条批注，目标滚动到屏幕垂直居中
关键：ScrollIntoView 后再 SmallScroll 上移，让目标落在屏幕中间
"""
import sys, os, json, subprocess, tempfile, base64

PS = r'''$ErrorActionPreference = "Continue"
$payload = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("%(B64)s")) | ConvertFrom-Json
$docPath = "%(DOCX)s"
$author  = "%(AUTHOR)s"
$delay   = %(DELAY)d
$center  = %(CENTER)d

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
try { $k.UserName = $author } catch {}

$d = $null
try { foreach ($doc in $k.Documents) { if ($doc.FullName -eq $docPath) { $d = $doc } } } catch {}
if ($d -eq $null) { $d = $k.Documents.Open($docPath) }

# 窗口最大化置前
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

$n = 0; $miss = 0
foreach ($it in $payload) {
  $rng = $d.Content
  $f = $rng.Find
  $f.ClearFormatting()
  $f.Text = $it.find
  $f.Forward = $true
  $f.Wrap = 0
  if ($f.Execute()) {
    $d.Comments.Add($rng, $it.text) | Out-Null
    $n++
    # 居中：先 ScrollIntoView，再上移若干行
    try {
      $d.ActiveWindow.ScrollIntoView($rng)
      Start-Sleep -Milliseconds 300
      if ($center -gt 0) { $d.ActiveWindow.SmallScroll(0, -$center, 0, 0) }
    } catch {}
    Start-Sleep -Milliseconds $delay
    Write-Output ("[" + $n + "] " + $it.find)
  } else { $miss++; Write-Output ("MISS " + $it.find) }
}
$d.Save()
Write-Output ("TOTAL=" + $d.Comments.Count + " MISS=" + $miss)
'''

def run(docx, issues, author="Teacher", delay=2000, center=9):
    b64 = base64.b64encode(json.dumps(issues, ensure_ascii=False).encode("utf-8")).decode()
    ps = PS % {"B64": b64, "DOCX": docx.replace("\\", "\\\\"),
               "AUTHOR": author, "DELAY": delay, "CENTER": center}
    f = tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig")
    f.write(ps); f.close()
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", f.name],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    os.unlink(f.name)
    return r.stdout, r.stderr

if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    out, err = run(cfg["docx"], cfg["issues"], cfg.get("author", "Teacher"),
                   cfg.get("delay", 2000), cfg.get("center", 9))
    print(out.strip())
    if err.strip():
        print("ERR:", err[-400:])
