"""単一の前面アプリを管理する、描画・実機I/Oに依存しない状態機械。"""
from .sdk import FrameInput, Session

RIGHT, LEFT, DOWN, UP, START, RESET, BACK, FN = (1 << n for n in range(8))


class ResourceLedger:
    """信頼したホスト側サービスの解放処理を、起動単位でまとめる。"""

    def __init__(self):
        self._resources = []

    @property
    def count(self):
        return len(self._resources)

    def acquire(self, owner, name, cleanup):
        self._resources.append((owner, name, cleanup))

    def release(self, owner):
        owned = [row for row in self._resources if row[0] == owner]
        self._resources = [row for row in self._resources if row[0] != owner]
        errors = []
        for _, name, cleanup in reversed(owned):
            try:
                cleanup()
            except Exception as error:
                errors.append((name, str(error)))
        return errors


class Home:
    def __init__(self, repository, session_factory=Session):
        self.repository = repository
        self.session_factory = session_factory
        self.ledger = ResourceLedger()
        self.input = FrameInput()
        self.mode = 'home'
        self.session = None
        self.active_id = None
        self.apps = []
        self.selected = 0
        self.failures = {}
        self.disabled = set()
        self.notice = ''
        self._generation = 0
        self._owner = None
        self.refresh()

    @property
    def selected_id(self):
        return self.apps[self.selected]['id'] if self.apps else None

    @property
    def commands(self):
        return list(self.session.commands) if self.session is not None else []

    def refresh(self):
        previous = self.selected_id
        self.apps = []
        for name in sorted(self.repository.index):
            if name in self.disabled:
                continue
            try:
                manifest = self.repository.current(name)
                if manifest:
                    self.apps.append(manifest)
            except (ValueError, OSError, KeyError, TypeError) as error:
                self.failures[name] = str(error)
        names = [app['id'] for app in self.apps]
        self.selected = names.index(previous) if previous in names else 0

    def _require_home(self):
        if self.mode != 'home':
            raise RuntimeError('management requires home')

    def install(self, manifest, blob):
        self._require_home()
        self.repository.install(manifest, blob)
        self.disabled.discard(manifest['id'])
        self.failures.pop(manifest['id'], None)
        self.refresh()
        self.notice = '更新しました'

    def uninstall(self, name):
        self._require_home()
        self.repository.uninstall(name)
        self.disabled.discard(name)
        self.failures.pop(name, None)
        self.refresh()
        self.notice = '削除しました'

    def _release(self):
        errors = self.ledger.release(self._owner)
        self.session = None
        self.active_id = None
        self._owner = None
        self.mode = 'release'
        if errors:
            self.notice = '資源の解放に失敗しました'

    def _failed(self, name, error):
        self._release()
        self.failures[name] = str(error)
        self.notice = 'アプリを停止しました'
        try:
            self.repository.quarantine(name)
        except (ValueError, OSError, KeyError, TypeError) as quarantine_error:
            self.disabled.add(name)
            self.failures[name] += '; quarantine: ' + str(quarantine_error)
        self.refresh()

    def _launch(self, held, now_ms):
        name = self.selected_id
        if name is None:
            return
        self._generation += 1
        self._owner = (name, self._generation)
        try:
            manifest, blob = self.repository.load(name)
            self.session = self.session_factory(blob, manifest, initial_held=held, now_ms=now_ms)
            self.ledger.acquire(self._owner, 'vm', self.session.close)
            self.active_id = name
            self.mode = 'running'
            self.notice = ''
        except Exception as error:
            self._failed(name, error)

    def frame(self, held, now_ms):
        _, pressed, _ = self.input.sample(held)
        if self.mode == 'release':
            if held == 0:
                self.mode = 'home'
            return
        if self.mode == 'home':
            if self.apps:
                if pressed & DOWN:
                    self.selected = (self.selected + 1) % len(self.apps)
                elif pressed & UP:
                    self.selected = (self.selected - 1) % len(self.apps)
                if pressed & START:
                    self._launch(held, now_ms)
            return
        # システムの終了キーはアプリへ渡す前に処理する。
        if held & (FN | BACK) == (FN | BACK):
            self._release()
            self.notice = 'ホームに戻ります'
            return
        try:
            if self.session.frame(held, now_ms):
                self._release()
                self.notice = 'ホームに戻ります'
        except Exception as error:
            self._failed(self.active_id, error)

    def close(self):
        self._release()
        self.mode = 'home'
        self.input = FrameInput()
