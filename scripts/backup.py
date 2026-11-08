# -*- coding: utf-8 -*-
"""
backup.py —— 批注前自动备份
用法: python backup.py paper.docx
备份到同目录 _批注备份/，文件名带时间戳和 SHA256 前12位
"""
import sys, os, shutil, hashlib, datetime, glob, zipfile

def sha12(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()[:12]

def verify(path):
    """验证 docx 结构完整"""
    try:
        z = zipfile.ZipFile(path)
        if z.testzip() is not None:
            return False, "ZIP损坏"
        from lxml import etree
        for part in ('word/document.xml', '[Content_Types].xml'):
            etree.fromstring(z.read(part))
        d = z.read('word/document.xml').decode('utf-8')
        c = z.read('word/comments.xml').decode('utf-8') if 'word/comments.xml' in z.namelist() else ''
        n1 = c.count('<w:comment ')
        n2, n3, n4 = d.count('commentRangeStart'), d.count('commentRangeEnd'), d.count('commentReference')
        z.close()
        if n1 and not (n1 == n2 == n3 == n4):
            return False, "批注锚点不一致 %d/%d/%d/%d" % (n1,n2,n3,n4)
        return True, "OK 批注%d 结构完整" % n1
    except Exception as e:
        return False, str(e)

def backup(path, tag=''):
    d = os.path.dirname(os.path.abspath(path))
    base = os.path.splitext(os.path.basename(path))[0][:24]
    bakdir = os.path.join(d, '_批注备份')
    os.makedirs(bakdir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    h = sha12(path)
    suffix = ('_' + tag) if tag else ''
    dst = os.path.join(bakdir, '%s_%s%s_%s.docx' % (base, ts, suffix, h))
    shutil.copyfile(path, dst)
    ok, msg = verify(dst)
    return dst, h, ok, msg

if __name__ == '__main__':
    path = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else ''
    dst, h, ok, msg = backup(path, tag)
    print("备份: %s" % os.path.basename(dst))
    print("SHA:  %s" % h)
    print("校验: %s %s" % ("✓" if ok else "✗", msg))
