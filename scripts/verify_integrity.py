# -*- coding: utf-8 -*-
import sys, zipfile
from lxml import etree
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s'%(W,t.split(':')[1])
def texts(p):
    z=zipfile.ZipFile(p); r=etree.fromstring(z.read('word/document.xml'))
    out=[]
    for para in r.find(q('w:body')):
        if para.tag!=q('w:p'): continue
        # 排除批注引用run的文本（本身为空），统计正文文本
        out.append(''.join(t.text or '' for t in para.findall('.//'+q('w:t'))))
    return out
a=texts(sys.argv[1]); b=texts(sys.argv[2])
print('段落数 原=%d 新=%d'%(len(a),len(b)))
diff=[(i,x,y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
print('正文差异段数 =',len(diff))
for i,x,y in diff[:5]: print('  ',i,repr(x),'->',repr(y))
print('结论：正文文字%s'%('完全一致，未被改动' if not diff and len(a)==len(b) else '有变化'))
