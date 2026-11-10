#!/usr/bin/env python3
"""Build the GitHub Pages site from the Markdown pages.

The Markdown (README.md and works/<slug>/*.md) stays the only source. This script
reads it and writes a site with its own design: callout boxes, certainty badges,
source links to the reference page, figures with captions, and a table of contents.

Usage: python3 scripts/build_site.py [--out _site] [--check]
--check verifies the built site and exits 1 with NG lines when anything is broken.
"""
import argparse
import html
import pathlib
import posixpath
import re
import shutil
import sys
import urllib.parse

import yaml
from markdown_it import MarkdownIt

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_URL = 'https://github.com/maco165/anime-guide'
SITE_URL = 'https://maco165.github.io/anime-guide/'
ASSETS = ROOT / 'site'
# Sections of the README written for contributors, not readers.
README_SKIP = {'作品ごとの置き場所'}
WORKS_SECTION = '公開している作品'
# Repository files that the site does not render; links to them go to GitHub.
REPO_ONLY = {'CONTRIBUTING.md', 'LICENSE'}
CALLOUTS = {
    'NOTE': '補足', 'TIP': 'ヒント', 'IMPORTANT': '重要',
    'WARNING': '注意', 'CAUTION': '確かさの注意',
}
MARKS = [
    (re.compile(r'公式'), 'official'),
    (re.compile(r'複数サイト|\d+ サイトで一致'), 'multi'),
    (re.compile(r'1 サイトのみ'), 'single'),
    (re.compile(r'説が割れている'), 'split'),
]

md = MarkdownIt('commonmark', {'html': True}).enable('table')


# ---------- reading ----------

def split_front_matter(text):
    if text.startswith('---\n'):
        end = text.index('\n---\n', 4)
        return yaml.safe_load(text[4:end]) or {}, text[end + 5:]
    return {}, text


def slugify(text, seen):
    """GitHub's heading anchor: lowercase, drop punctuation, spaces to hyphens."""
    plain = re.sub(r'<[^>]+>', '', html.unescape(text)).strip().lower()
    slug = re.sub(r'[^\w\- ]', '', plain).replace(' ', '-')
    n = seen.get(slug, 0)
    seen[slug] = n + 1
    return slug if n == 0 else f'{slug}-{n}'


def split_sections(body):
    """Split Markdown into (h2 title, text) pairs. The text before the first h2 has title None."""
    parts, title, buf, fence = [], None, [], False
    for line in body.splitlines(keepends=True):
        if line.startswith('```'):
            fence = not fence
        if not fence and line.startswith('## '):
            parts.append((title, ''.join(buf)))
            title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    parts.append((title, ''.join(buf)))
    return parts


def read_works(readme_section):
    """Read the works table: [(slug, title, card, [(label, page)])]."""
    works = []
    for line in readme_section.splitlines():
        card = re.search(r'<img src="works/([^/]+)/([^"]+)"[^>]*alt="([^"]+)"', line)
        if not card:
            continue
        slug, card_file, title = card.groups()
        cells = line.split('|')
        pages = re.findall(r'\[([^\]]+)\]\(works/' + re.escape(slug) + r'/([^)]+)\.md\)', cells[2])
        works.append({'slug': slug, 'title': title, 'card': card_file, 'pages': pages})
    return works


def load_sources(work_dir):
    path = work_dir / 'sources.yml'
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return {s['id']: s for s in data.get('sources', [])}


# ---------- rendering ----------

def rewrite_href(href, page_dir):
    """Point links at the built site: .md to .html, repository-only files to GitHub."""
    if re.match(r'^[a-z]+:|^#', href):
        return href
    path, _, frag = href.partition('#')
    target = posixpath.normpath(posixpath.join(page_dir, path)) if path else ''
    if target in REPO_ONLY:
        return f'{REPO_URL}/blob/main/{target}' + (f'#{frag}' if frag else '')
    if path.endswith('.md'):
        if posixpath.basename(path) == 'README.md':
            new = posixpath.join(posixpath.dirname(path), 'index.html')
        else:
            new = path[:-3] + '.html'
        return new + (f'#{frag}' if frag else '')
    return href


def flow_steps(code):
    """Render a linear Mermaid flowchart (A --> B --> C) as a row of steps, else None."""
    lines = [ln.strip() for ln in code.strip().splitlines()]
    if not lines or not lines[0].startswith('flowchart'):
        return None
    labels = re.findall(r'\w+\["([^"]+)"\]', ' '.join(lines[1:]))
    if len(lines) != 2 or not labels:
        return None
    items = ''.join(f'<li>{html.escape(t)}</li>' for t in labels)
    return f'<ol class="flow">{items}</ol>'


def render(markdown_text, page_dir, sources=None, ref_page=None):
    """Render Markdown and apply the site's treatments. Returns (html, toc)."""
    out = md.render(markdown_text)

    def mermaid(m):
        steps = flow_steps(html.unescape(m.group(1)))
        return steps or m.group(0)
    out = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>', mermaid, out, flags=re.S)

    out = re.sub(r'(href|src)="([^"]+)"',
                 lambda m: f'{m.group(1)}="{rewrite_href(m.group(2), page_dir)}"', out)

    def callout(m):
        kind = m.group(1)
        return (f'<aside class="callout callout-{kind.lower()}"><p class="callout-label">'
                f'{CALLOUTS.get(kind, kind)}</p>\n<p>')
    out = re.sub(r'<blockquote>\s*<p>\[!(\w+)\]\s*', callout, out)
    out = re.sub(r'(<aside class="callout[^>]*>.*?)</blockquote>', r'\1</aside>', out, flags=re.S)

    def mark(m):
        text = m.group(1)
        for pattern, cls in MARKS:
            if pattern.fullmatch(text):
                return f'<span class="mark mark-{cls}">{text}</span>'
        return m.group(0)
    out = re.sub(r'<code>([^<]+)</code>', mark, out)
    out = re.sub(r'(</span>)×(\d+)', r'\1<span class="mark-count">×\2</span>', out)

    def src_link(m):
        sid = m.group(1)
        src = (sources or {}).get(sid, {})
        tip = ' / '.join(x for x in (src.get('kind'), src.get('rights_holder')) if x)
        title = f' title="{html.escape(tip)}"' if tip else ''
        return f'<a class="src" href="{ref_page}#{sid}"{title}>{sid}</a>'
    if ref_page:
        out = re.sub(r'(?<!<code>)\[(src-\d{3})\](?!</code>)', src_link, out)
    out = re.sub(r'<td>(src-\d{3})</td>', r'<td id="\1" class="src-id">\1</td>', out)

    out = re.sub(r'【(考察|見立て)】', r'<span class="opinion">\1</span>', out)
    out = re.sub(r'<p>(<img [^>]+>)</p>\s*<p><sub>(.*?)</sub></p>',
                 r'<figure>\1<figcaption>\2</figcaption></figure>', out, flags=re.S)
    out = re.sub(r'<p>(<img [^>]+>)</p>', r'<figure>\1</figure>', out)
    out = re.sub(r'<img ', '<img loading="lazy" ', out)
    out = re.sub(r'<thead>\s*<tr>(?:\s*<th[^>]*>\s*</th>)+\s*</tr>\s*</thead>\s*', '', out)
    out = re.sub(r'(<table>.*?</table>)', r'<div class="table-wrap">\1</div>', out, flags=re.S)

    seen, toc = {}, []

    def heading(m):
        level, inner = int(m.group(1)), m.group(2)
        hid = slugify(inner, seen)
        if level in (2, 3):
            toc.append((level, hid, re.sub(r'<[^>]+>', '', inner)))
        return f'<h{level} id="{hid}">{inner}</h{level}>'
    out = re.sub(r'<h([1-6])>(.*?)</h\1>', heading, out)
    return out, toc


def summary(content, limit=110):
    """The first body paragraph as plain text, for the page description."""
    text = re.sub(r'(?s)<aside.*?</aside>|<div class="table-wrap">.*?</div>|<figure>.*?</figure>', '', content)
    m = re.search(r'(?s)<p>(.*?)</p>', text)
    if not m:
        return ''
    plain = re.sub(r'<span class="mark[^"]*">.*?</span>|<a class="src"[^>]*>.*?</a>|<rt>.*?</rt>', '', m.group(1))
    plain = html.unescape(re.sub(r'<[^>]+>', '', plain))
    plain = re.sub(r'\s+', ' ', plain).strip()
    return plain if len(plain) <= limit else plain[:limit].rstrip() + '…'


def layout(title, body, root, description, path, extra_class=''):
    """Wrap a page. path is the page's path inside the site ('' for the top page)."""
    url = SITE_URL + path
    t, d = html.escape(title), html.escape(description)
    head = f'''<meta name="description" content="{d}">
<link rel="canonical" href="{url}">
<link rel="icon" type="image/svg+xml" href="{root}favicon.svg">
<meta property="og:type" content="{'website' if not path else 'article'}">
<meta property="og:site_name" content="anime-guide">
<meta property="og:locale" content="ja_JP">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE_URL}og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">'''
    return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
{head}
<link rel="stylesheet" href="{root}style.css">
</head>
<body class="{extra_class}">
<header class="site-header"><a class="site-name" href="{root}index.html">anime-guide</a>
<nav><a href="{REPO_URL}/issues/new">誤りを指摘する</a><a href="{REPO_URL}">GitHub</a></nav></header>
{body}
<footer class="site-footer"><p>非公式の解説です。作品の権利者や制作会社とは関係ありません。内容は AI (Claude) がまとめています。</p>
<p><a href="{root}index.html#ライセンス">ライセンス</a> · <a href="{REPO_URL}">GitHub</a> · <a href="{REPO_URL}/issues/new">誤りを指摘する</a></p></footer>
</body>
</html>
'''


def build_index(readme, out):
    _, body = split_front_matter(readme)
    sections = split_sections(body)
    head = sections[0][1]
    h1 = re.search(r'^# (.+)$', head, re.M).group(1).strip()
    tagline = re.search(r'^\*\*(.+)\*\*$', head, re.M).group(1)
    chips = re.findall(r'!\[([^\]]+)\]\(https://img\.shields\.io', head)
    links = [(t, h) for t, h in re.findall(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', head)
             if not h.startswith(SITE_URL) and not h.startswith('https://img.shields.io')]
    lead = re.sub(r'(?s)<div[^>]*>.*?</div>', '', head)
    lead = re.sub(r'(?m)^# .*$', '', lead)

    works = []
    parts = []
    for title, text in sections[1:]:
        if title in README_SKIP:
            continue
        if title == WORKS_SECTION:
            works = read_works(text)
            parts.append(render_works(works, title))
            continue
        content, _ = render(text, '')
        parts.append(f'<section class="block"><h2 id="{slugify(title, {})}">{html.escape(title)}</h2>\n{content}</section>')

    chip_html = ''.join(f'<li>{html.escape(c)}</li>' for c in chips)
    # ボタンは主な操作 1 つと補助の操作 1 つだけにする。README の先頭のほかのリンク (CONTRIBUTING など) は
    # 本文の節からたどれる
    link_html = ''.join(
        f'<a class="button{" primary" if i == 0 else ""}" href="{rewrite_href(h, "")}">{html.escape(t)}</a>'
        for i, (t, h) in enumerate(links[:2]))
    lead_html, _ = render(lead, '')
    body_html = f'''<div class="hero"><div class="hero-inner">
<h1>{html.escape(h1)}</h1>
<p class="tagline">{html.escape(tagline)}</p>
<ul class="chips">{chip_html}</ul>
<div class="actions">{link_html}</div>
</div></div>
<main class="home">
{lead_html}
{''.join(parts)}
</main>'''
    (out / 'index.html').write_text(layout(f'{h1} | {tagline}', body_html, '', tagline, '', 'page-home'),
                                    encoding='utf-8')
    return works


def render_works(works, title):
    cards = []
    for w in works:
        first = f'works/{w["slug"]}/{w["pages"][0][1]}.html' if w['pages'] else '#'
        pages = ''.join(f'<li><a href="works/{w["slug"]}/{p}.html">{html.escape(label)}</a></li>'
                        for label, p in w['pages'])
        cards.append(f'''<article class="work-card">
<a class="work-cover" href="{first}"><img src="works/{w["slug"]}/{w["card"]}" alt="{html.escape(w["title"])}"></a>
<ul class="work-pages">{pages}</ul>
</article>''')
    return (f'<section class="block"><h2 id="{slugify(title, {})}">{html.escape(title)}</h2>'
            f'<div class="works">{"".join(cards)}</div></section>')


def build_page(src, out, work, sources):
    meta, body = split_front_matter(src.read_text(encoding='utf-8'))
    body = re.sub(r'(?m)^\[← [^\n]*\n', '', body, count=1)
    h1 = re.search(r'^# (.+)$', body, re.M)
    title = h1.group(1).strip() if h1 else src.stem
    body = re.sub(r'(?m)^# .+\n', '', body, count=1)
    page_dir = f'works/{src.parent.name}'
    content, toc = render(body, page_dir, sources, 'references.html')

    nav = ''
    if work:
        nav = ''.join(
            f'<li{" class=current" if p == src.stem else ""}><a href="{p}.html">{html.escape(label)}</a></li>'
            for label, p in work['pages'])
        nav = f'<nav class="work-nav" aria-label="{html.escape(work["title"])} のページ"><ul>{nav}</ul></nav>'
    facts = ''.join(f'<li>{html.escape(str(meta[k]))}</li>' for k in ('version', 'spoiler') if meta.get(k))
    toc_html = ''.join(f'<li class="toc-{lv}"><a href="#{hid}">{html.escape(html.unescape(t))}</a></li>'
                       for lv, hid, t in toc)
    work_title = work['title'] if work else ''
    body_html = f'''<div class="page-head"><div class="page-head-inner">
<p class="work-name"><a href="../../index.html">anime-guide</a> / {html.escape(work_title)}</p>
<h1>{html.escape(title)}</h1>
<ul class="facts">{facts}</ul>
{nav}
</div></div>
<div class="page">
<aside class="toc"><p>このページの目次</p><ol>{toc_html}</ol></aside>
<main class="content">
{content}
</main>
</div>'''
    target = out / page_dir / f'{src.stem}.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(layout(f'{title} | anime-guide', body_html, '../../', summary(content) or title,
                             f'{page_dir}/{src.stem}.html', 'page-work'),
                      encoding='utf-8')


def published_pages():
    return [ROOT / 'README.md'] + sorted((ROOT / 'works').glob('*/*.md'))


def write_sitemap(out):
    pages = sorted(p.relative_to(out).as_posix() for p in out.rglob('*.html'))
    urls = ''.join(f'  <url><loc>{SITE_URL}{"" if p == "index.html" else p}</loc></url>\n' for p in pages)
    (out / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n', encoding='utf-8')


def build(out):
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for asset in ('style.css', 'favicon.svg', 'og.png'):
        shutil.copy(ASSETS / asset, out / asset)
    works = build_index((ROOT / 'README.md').read_text(encoding='utf-8'), out)
    by_slug = {w['slug']: w for w in works}
    for work_dir in sorted(p for p in (ROOT / 'works').iterdir() if p.is_dir()):
        sources = load_sources(work_dir)
        dest = out / 'works' / work_dir.name
        dest.mkdir(parents=True, exist_ok=True)
        for asset in work_dir.glob('*.svg'):
            shutil.copy(asset, dest / asset.name)
        if (work_dir / 'figures').is_dir():
            shutil.copytree(work_dir / 'figures', dest / 'figures')
        for page in sorted(work_dir.glob('*.md')):
            build_page(page, out, by_slug.get(work_dir.name), sources)
    write_sitemap(out)


# ---------- checking ----------

def check(out):
    ng = []
    built = sorted(out.rglob('*.html'))
    if len(built) != len(published_pages()):
        ng.append(f'page count: {len(published_pages())} Markdown pages, {len(built)} HTML pages')
    for asset in ('favicon.svg', 'og.png'):
        if not (out / asset).exists():
            ng.append(f'missing {asset}')
    sitemap = (out / 'sitemap.xml').read_text(encoding='utf-8') if (out / 'sitemap.xml').exists() else ''
    ids = {}
    for page in built:
        ids[page] = set(re.findall(r'\sid="([^"]+)"', page.read_text(encoding='utf-8')))
    for page in built:
        text = page.read_text(encoding='utf-8')
        rel = page.relative_to(out)
        url = SITE_URL + ('' if rel.as_posix() == 'index.html' else rel.as_posix())
        if f'<link rel="canonical" href="{url}">' not in text:
            ng.append(f'{rel}: canonical is not {url}')
        desc = re.search(r'<meta name="description" content="([^"]*)">', text)
        title = re.search(r'<title>(.*?)</title>', text)
        if not desc or not desc.group(1) or (title and title.group(1).startswith(desc.group(1) + ' |')):
            ng.append(f'{rel}: description is empty or only repeats the title')
        if url not in sitemap:
            ng.append(f'{rel}: not in sitemap.xml')
        if re.search(r'\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]', text):
            ng.append(f'{rel}: callout marker left as text')
        if re.search(r'(?<!<code>)\[src-\d{3}\](?!</code>)', text):
            ng.append(f'{rel}: source id left unlinked')
        for attr, href in re.findall(r'(href|src)="([^"]+)"', text):
            if re.match(r'^[a-z]+:', href):
                continue
            path, _, frag = urllib.parse.unquote(html.unescape(href)).partition('#')
            target = (page.parent / path).resolve() if path else page
            if path.endswith('.md'):
                ng.append(f'{rel}: link to Markdown {href}')
            elif not target.exists():
                ng.append(f'{rel}: missing {attr} {href}')
            elif frag and target.suffix == '.html' and frag not in ids.get(target, set()):
                ng.append(f'{rel}: missing anchor {href}')
    return ng


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default='_site')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    out = (ROOT / args.out).resolve()
    build(out)
    pages = len(list(out.rglob('*.html')))
    if args.check:
        ng = check(out)
        for line in ng:
            print('NG', line)
        if ng:
            sys.exit(1)
        print(f'OK {pages} pages')
    else:
        print(f'built {pages} pages into {out}')


if __name__ == '__main__':
    main()
