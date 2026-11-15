"""追跡Markdownのローカル参照を検査する。ネットワークや実機へ接続しない。"""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def heading_ids(text):
    counts = {}
    result = set()
    for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', text, re.M):
        slug = re.sub(r'[^\w\-\s]', '', heading.lower()).replace(' ', '-')
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(slug if not count else f'{slug}-{count}')
    return result


def check_markdown(root, paths):
    root = Path(root).resolve()
    count = 0
    for name in paths:
        path = root / name
        if path.suffix != '.md':
            continue
        text = re.sub(r'^```[^\n]*\n.*?^```\s*$', '', path.read_text(), flags=re.M | re.S)
        for target in re.findall(r'\]\(([^)]+)\)', text):
            target = target.strip('<>')
            if re.match(r'^[a-zA-Z][\w+.-]*:', target):
                continue
            relative, _, anchor = target.partition('#')
            destination = (path.parent / unquote(relative)).resolve() if relative else path
            if not destination.is_relative_to(root) or not destination.exists():
                raise ValueError(f'{name}: missing or escaping local link: {target}')
            if anchor and destination.suffix == '.md' and unquote(anchor) not in heading_ids(destination.read_text()):
                raise ValueError(f'{name}: missing local heading: {target}')
            count += 1
    return count


def main():
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().strip('\0').split('\0')
    count = check_markdown(ROOT, paths)
    print(f'Markdown local links: {count} passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
