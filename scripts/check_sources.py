#!/usr/bin/env python3
"""Check a work's source ledger against its pages and figures.

Usage: python3 scripts/check_sources.py works/<slug>
Exits 1 and prints NG lines when any check fails.
"""
import pathlib
import re
import sys
import urllib.parse

import yaml

PERMISSIONS = {'未依頼', '依頼中', '許諾', '拒否', '不要'}
ID_FORMAT = re.compile(r'src-\d{3}')
ID_TOKEN = re.compile(r'(?<![\w-])src-[\w-]*')
GENERATED = 'references.md'
FIGURE_SOURCES = 'figure-sources.yml'
UNREACHABLE = 'unreachable.yml'


def normalize_url(url):
    """Treat percent-encoding, a leading www. and a trailing slash as the same URL."""
    parts = urllib.parse.urlsplit(urllib.parse.unquote(url))
    host = parts.netloc.lower().removeprefix('www.')
    return host, parts.path.rstrip('/'), parts.query


def find_ids(text):
    """Return every id-like token, ignoring URLs."""
    return ID_TOKEN.findall(re.sub(r'https?://[^\s)\]]+', ' ', text))


def strip_front_matter(text):
    return re.sub(r'\A---\n.*?\n---\n', '', text, flags=re.S)


def check(work):
    errors = []
    ledger_path = work / 'sources.yml'
    if not ledger_path.is_file():
        return [f'{ledger_path}: not found']
    ledger = yaml.safe_load(ledger_path.read_text(encoding='utf-8'))['sources']

    seen_urls = {}
    seen_ids = set()
    for entry in ledger:
        sid = entry['id']
        if not ID_FORMAT.fullmatch(sid):
            errors.append(f'sources.yml: malformed id {sid}')
        if sid in seen_ids:
            errors.append(f'sources.yml: duplicate id {sid}')
        seen_ids.add(sid)
        key = normalize_url(entry['url'])
        if key in seen_urls:
            errors.append(f'sources.yml: {sid} has the same URL as {seen_urls[key]}: {entry["url"]}')
        seen_urls.setdefault(key, sid)
        if entry.get('permission') not in PERMISSIONS:
            errors.append(f'sources.yml: {sid} has permission {entry.get("permission")!r}')

    used = set()
    files = sorted(work.glob('*.md')) + sorted(work.glob('figures/*.svg'))
    figure_sources = work / FIGURE_SOURCES
    if figure_sources.is_file():
        files.append(figure_sources)
    for path in files:
        text = path.read_text(encoding='utf-8')
        name = path.relative_to(work)
        for token in sorted(set(find_ids(text)) - seen_ids):
            errors.append(f'{name}: {token} is not in sources.yml')
        if path.name != GENERATED:
            body = strip_front_matter(text) if path.suffix == '.md' else text
            used.update(find_ids(body))
    for entry in ledger:
        # A refused source stays in the ledger as the record of the removal request.
        if entry['id'] not in used and entry.get('permission') != '拒否':
            errors.append(f'sources.yml: {entry["id"]} is not used by any page or figure')

    unreachable = work / UNREACHABLE
    if unreachable.is_file():
        for entry in yaml.safe_load(unreachable.read_text(encoding='utf-8'))['unreachable']:
            if entry.get('url') and normalize_url(entry['url']) in seen_urls:
                errors.append(f'{UNREACHABLE}: {entry["url"]} is also in sources.yml')
    return errors


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    errors = check(pathlib.Path(sys.argv[1]))
    if errors:
        print('NG')
        print('\n'.join(errors))
        sys.exit(1)
    print('OK')


if __name__ == '__main__':
    main()
