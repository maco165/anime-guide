#!/usr/bin/env python3
"""Generate a work's references.md from its source ledger, pages and figures.

Usage: python3 scripts/build_references.py works/<slug> [--check]
With --check, nothing is written and the exit status is 1 if references.md is not up to date.
"""
import argparse
import pathlib
import re
import sys
import urllib.parse

import yaml

OUTPUT = 'references.md'
# Page stem -> label, in display order. Other pages follow in file name order.
PAGE_LABELS = {
    'world': '世界観',
    'abilities': '能力',
    'seven-sins': '七つの大罪',
    'column': 'コラム',
    'characters': 'キャラクター',
    'audience': '誰向け',
}
CATEGORIES = ['公式', '事典・Wiki', '学術', 'データベース', '解説・まとめ', '考察', 'その他']
# First match wins, so the order matters: 「研究機関の記事」 is 学術, not 解説・まとめ.
CATEGORY_RULES = [
    ('その他', r'インタビュー|ファンの整理|本人の感想'),
    ('公式', r'公式サイト'),
    ('事典・Wiki', r'事典|wiki|ウィキ'),
    ('データベース', r'データベース|年表'),
    ('学術', r'論文|学術誌|専門誌|大学|研究機関|図書館|博物館|原典|教会の文書'),
    ('考察', r'論考|評論|個人'),
    ('解説・まとめ', r'解説|まとめ|記事|ブログ'),
]
FIGURE_IMAGE = re.compile(r'^!\[.*\]\(figures/(?P<file>[^)]+\.svg)\)$')
FIGURE_CAPTION = re.compile(r'^<sub>図 (?P<figure>\d+-\d+)[ :]')
SOURCE_ID = re.compile(r'(?<![\w-])src-\d+')


def category_of(kind):
    for name, pattern in CATEGORY_RULES:
        if re.search(pattern, kind, re.I):
            return name
    return 'その他'


def split_page(text):
    match = re.match(r'---\n(.*?)\n---\n(.*)', text, re.S)
    if not match:
        return {}, text
    return yaml.safe_load(match[1]), match[2]


def find_pages(work):
    stems = [p.stem for p in work.glob('*.md') if p.name != OUTPUT]
    known = [s for s in PAGE_LABELS if s in stems]
    return known + sorted(s for s in stems if s not in PAGE_LABELS)


def parse_page(work, stem, figure_rows):
    """Return (front, figures, prose ids). A figure is a dict of number, title and ids."""
    front, body = split_page((work / f'{stem}.md').read_text(encoding='utf-8'))
    lines = body.split('\n')
    figures = []
    prose = []
    index = 0
    while index < len(lines):
        image = FIGURE_IMAGE.match(lines[index])
        if not image:
            prose.append(lines[index])
            index += 1
            continue
        following = next((n for n in range(index + 1, len(lines)) if lines[n].strip()), None)
        caption = FIGURE_CAPTION.match(lines[following]) if following else None
        if not caption:
            sys.exit(f'{stem}.md:{index + 1}: a figure needs a numbered caption below it')
        svg = (work / 'figures' / image['file']).read_text(encoding='utf-8')
        title = re.search(r'<title[^>]*>(.*?)</title>', svg, re.S)
        number = caption['figure']
        rows = figure_rows.get(number, {}).get('rows', [])
        ids = SOURCE_ID.findall(lines[following]) + SOURCE_ID.findall(svg)
        ids += [i for row in rows for i in row['sources']]
        figures.append({
            'number': number,
            'title': title[1] if title else '',
            'ids': sorted(set(ids)),
            'detail': figure_rows.get(number),
        })
        index = following + 1
    return front, figures, set(SOURCE_ID.findall('\n'.join(prose)))


def cell(text):
    return str(text).replace('|', '\\|')


def source_link(sid, ledger):
    if sid not in ledger:
        sys.exit(f'{sid} is not in sources.yml')
    return f'[[{sid}]]({ledger[sid]["url"]})'


def url_link(url):
    return f'[{urllib.parse.unquote(url)}]({url})'


def mark_text(mark):
    return mark if mark == '印なし' else f'`{mark}`'


def figure_anchor(stem, number):
    return f'{PAGE_LABELS.get(stem, stem)} 図 {number}'


def usage_cell(sid, pages):
    parts = []
    for stem, page in pages.items():
        places = [f'図 {f["number"]}' for f in page['figures'] if sid in f['ids']]
        if sid in page['prose']:
            places.append('本文')
        if places:
            parts.append(f'[{PAGE_LABELS.get(stem, stem)}]({stem}.md) {"、".join(places)}')
    return '<br>'.join(parts)


def source_sections(ledger, pages):
    groups = {name: [] for name in CATEGORIES}
    for sid, entry in ledger.items():
        groups[category_of(entry['kind'])].append(sid)
    out = ['## 件数', '', '| 種類 | 件数 |', '| --- | --- |']
    out += [f'| {name} | {len(groups[name])} |' for name in CATEGORIES]
    out += [f'| 合計 | {len(ledger)} |', '', '## 出典の一覧', '']
    out += ['権利者の「不明」は、権利者を確定できなかったものです。許諾の「不要」は、出典の文章を転載していないものです。', '']
    for name in CATEGORIES:
        if not groups[name]:
            continue
        out += [f'### {name} ({len(groups[name])} 件)', '']
        out += ['| id | 種類 | URL | 権利者 | 確認日 | 許諾 | 使っている箇所 |', '| --- | --- | --- | --- | --- | --- | --- |']
        for sid in groups[name]:
            entry = ledger[sid]
            row = [sid, cell(entry['kind']), url_link(entry['url']), cell(entry.get('rights_holder', '')),
                   entry['checked_at'], entry['permission'], usage_cell(sid, pages)]
            out.append('| ' + ' | '.join(str(c) for c in row) + ' |')
        out.append('')
    return out


def row_table(rows, ledger, with_text):
    head = ['番号', '内容', '印', '出典'] if with_text else ['番号', '印', '出典']
    out = ['| ' + ' | '.join(head) + ' |', '| ' + ' | '.join(['---'] * len(head)) + ' |']
    for row in rows:
        links = ' '.join(source_link(i, ledger) for i in row['sources'])
        source = f'{links} {row["note"]}' if row.get('note') else links
        cells = [row['no'] or '']
        if with_text:
            cells.append(row['text'])
        cells += [mark_text(row['mark']), source]
        out.append('| ' + ' | '.join(cells) + ' |')
    return out


def figure_sections(ledger, pages):
    out = ['## 図ごとの出典', '', '番号の無い行は破線の枠で描いた内容です。', '']
    for stem, page in pages.items():
        current = None
        label = PAGE_LABELS.get(stem, stem)
        for figure in page['figures']:
            if not figure['ids']:
                continue
            detail = figure['detail'] or {}
            section = detail.get('section')
            heading = f'{label}: {section}' if section else label
            if heading != current:
                out += [f'### {heading}', '']
                current = heading
            out += [f'#### {figure_anchor(stem, figure["number"])}', '']
            out += [detail.get('note') or figure['title'], '']
            rows = detail.get('rows')
            if rows:
                out += row_table(rows, ledger, 'text' in rows[0])
            else:
                out.append(' '.join(source_link(i, ledger) for i in figure['ids']))
            out.append('')
    return out


def unreachable_section(work):
    path = work / 'unreachable.yml'
    if not path.is_file():
        return []
    entries = yaml.safe_load(path.read_text(encoding='utf-8'))['unreachable']
    out = [f'## 読めなかった元 ({len(entries)} 件)', '']
    out += ['調べるときに開けなかったページです。中身を読んでいないので、このリポジトリの記述の根拠にしていません。', '']
    out += ['| 元 | 理由 | 確認日 | 探していたページ |', '| --- | --- | --- | --- |']
    for entry in entries:
        name = entry.get('name') or urllib.parse.unquote(entry['url'])
        places = '、'.join(f'[{PAGE_LABELS.get(s, s)}]({s}.md)' for s in entry['pages'])
        out.append(f'| `{cell(name)}` | {cell(entry["reason"])} | {entry["checked_at"]} | {places} |')
    out.append('')
    return out


def build(work):
    ledger_entries = yaml.safe_load((work / 'sources.yml').read_text(encoding='utf-8'))['sources']
    ledger = {entry['id']: entry for entry in ledger_entries}
    figure_file = work / 'figure-sources.yml'
    details = yaml.safe_load(figure_file.read_text(encoding='utf-8'))['figures'] if figure_file.is_file() else {}
    pages = {}
    front = {}
    for stem in find_pages(work):
        rows = {str(f['figure']): f for f in details.get(stem, [])}
        page_front, figures, prose = parse_page(work, stem, rows)
        pages[stem] = {'figures': figures, 'prose': prose}
        for key in ('work', 'version', 'spoiler'):
            if key in page_front:
                front.setdefault(key, page_front[key])
    out = ['---'] + [f'{k}: {v}' for k, v in front.items()] + ['---', '']
    out += ['# 出典の参照ページ', '']
    out += ['このページの全ての出典と、使っているページと図の番号をまとめます。', '']
    out += ['**このページは設定のネタバレを含みます。**', '']
    out += ['`scripts/build_references.py` が `sources.yml`、`figure-sources.yml`、`unreachable.yml`、各ページ、図から生成するので、ここは直接書き換えません。', '']
    out += source_sections(ledger, pages)
    out += figure_sections(ledger, pages)
    out += unreachable_section(work)
    return '\n'.join(out).rstrip('\n') + '\n'


def main():
    parser = argparse.ArgumentParser(description='Generate references.md for a work.')
    parser.add_argument('work', type=pathlib.Path, help='works/<slug>')
    parser.add_argument('--check', action='store_true', help='exit 1 if references.md is not up to date')
    args = parser.parse_args()
    content = build(args.work)
    target = args.work / OUTPUT
    if args.check:
        current = target.read_text(encoding='utf-8') if target.is_file() else None
        if current != content:
            print(f'NG {target} is not up to date. Run scripts/build_references.py {args.work}')
            sys.exit(1)
        print('OK')
        return
    target.write_text(content, encoding='utf-8')
    print(f'wrote {target}')


if __name__ == '__main__':
    main()
