"""Mac用の実行・有限replay。シリアル接続やFlash操作は持たない。"""
import argparse
import json
import time
from pathlib import Path

from .build import build
from .display import key_mask, render
from .home import Home
from .repository import Repository, safe_read


def replay(repository, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    home = Home(Repository(repository))
    for name in ('counter', 'game'):
        manifest, blob = build(name, output / 'packages')
        home.install(manifest, blob)
    home.selected = next(i for i, app in enumerate(home.apps) if app['id'] == 'counter')
    home.notice = ''
    render(home).save(output / 'home.png')
    result = {'runtime': 'Wasmtime host / ABI 2', 'device_tested': False}
    trace = []

    def frame(held, now):
        home.frame(held, now)
        trace.append({'held': held, 'now_ms': now, 'mode': home.mode,
                      'active': home.active_id, 'resources': home.ledger.count})

    try:
        frame(16, 10)
        frame(0, 20)
        frame(1, 30)
        frame(0, 40)
        result['counter'] = home.session.debug('debug_value')
        render(home).save(output / 'counter.png')
        frame(192, 50)
        render(home).save(output / 'release.png')
        frame(0, 60)
        frame(4, 70)
        frame(0, 80)
        frame(16, 90)
        frame(0, 100)
        frame(16, 100)
        frame(1, 400)
        result['game_score'] = home.session.debug('debug_value')
        result['game_position'] = [home.session.debug('debug_x'), home.session.debug('debug_y')]
        render(home).save(output / 'game.png')
        frame(192, 410)
        frame(0, 420)
        result.update(active_resources=home.ledger.count, final_mode=home.mode, trace=trace)
    finally:
        home.close()
    (output / 'replay.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def run_window(home, scale=2, max_frames=None):
    import pygame
    if scale not in (1, 2, 3, 4):
        raise ValueError('scale')
    pygame.init()
    frames = 0
    try:
        screen = pygame.display.set_mode((320 * scale, 240 * scale))
        pygame.display.set_caption('Lab App OS — Mac host / Z:A X:B F:FN R:Reset')
        timer = pygame.time.Clock()
        start = time.monotonic_ns()
        keys = set()
        running = True
        while running and (max_frames is None or frames < max_frames):
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        keys.add(pygame.key.name(event.key))
                elif event.type == pygame.KEYUP:
                    keys.discard(pygame.key.name(event.key))
                elif event.type == pygame.WINDOWFOCUSLOST:
                    keys.clear()
            now = (time.monotonic_ns() - start) // 1000000
            home.frame(key_mask(keys), now)
            bitmap = render(home)
            surface = pygame.image.frombytes(bitmap.tobytes(), bitmap.size, 'RGB')
            screen.blit(pygame.transform.scale(surface, screen.get_size()), (0, 0))
            pygame.display.flip()
            frames += 1
            timer.tick(60)
    finally:
        home.close()
        pygame.quit()
    return frames


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('replay', 'run', 'install', 'remove'):
        child = sub.add_parser(name)
        child.add_argument('--repository', type=Path, default=Path('build/lab-os/apps'))
        if name == 'replay':
            child.add_argument('--output', type=Path, default=Path('reports/os-mvp/screens'))
        if name == 'run':
            child.add_argument('--scale', type=int, choices=(1, 2, 3, 4), default=2)
        if name == 'install':
            child.add_argument('package', type=Path)
        if name == 'remove':
            child.add_argument('app_id')
    args = parser.parse_args(argv)
    if args.command == 'replay':
        result = replay(args.repository, args.output)
        print(json.dumps({k: v for k, v in result.items() if k != 'trace'}, ensure_ascii=False))
        return 0
    home = Home(Repository(args.repository))
    if args.command == 'run':
        run_window(home, args.scale)
    elif args.command == 'install':
        manifest = json.loads(safe_read(args.package / 'manifest.json'))
        home.install(manifest, safe_read(args.package / 'app.wasm'))
    else:
        home.uninstall(args.app_id)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
