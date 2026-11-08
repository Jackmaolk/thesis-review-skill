# -*- coding: utf-8 -*-
"""audit_comments.py"""
import zipfile, re, sys

BANNED = ['AI', 'ai预', '智能生成', '模型', 'GPT', 'Claude', '机器人']

def audit(path):
    z = zipfile.ZipFile(path)
    if 'word/comments.xml' not in z.namelist():
        return {'comments': 0, 'authors': [], 'problems': ['no comments part'], 'texts': []}
    x = z.read('word/comments.xml').decode('utf-8')
    authors = sorted(set(re.findall(r'w:author="([^"]*)"', x)))
    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', x)
    problems = []
    for t in texts:
        for b in BANNED:
            if b.lower() in t.lower():
                problems.append('%s : %s' % (b, t[:40]))
                break
    return {'comments': x.count('<w:comment '), 'authors': authors,
            'problems': problems, 'texts': texts}

if __name__ == '__main__':
    r = audit(sys.argv[1])
    print('comments =', r['comments'])
    print('authors  =', r['authors'])
    print('problems =', r['problems'] if r['problems'] else 'none')