"""Временный каталог воркера с межпроцессной блокировкой и уборкой после аварий."""

import atexit
import logging
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


def _acquire(path, blocking=True):
    handle = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            msvcrt.locking(handle.fileno(), mode, 1)
        else:
            import fcntl

            fcntl.flock(
                handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            )
        return handle
    except (BlockingIOError, PermissionError):
        handle.close()
        if blocking:
            raise
        return None
    except Exception:
        handle.close()
        raise


@contextmanager
def _guard(root):
    handle = _acquire(root / ".gc.lock")
    try:
        yield
    finally:
        handle.close()


class TempWorkspace:
    """Изолирует временные файлы и удаляет только каталоги мёртвых воркеров."""

    def __init__(self, root=None):
        """Определяет общий корень без изменения настроек tempfile."""
        self.root = Path(
            root
            or os.getenv("APP_TEMP_ROOT")
            or Path(tempfile.gettempdir()) / "extract-text-workers"
        )
        self.directory = None
        self._owner = None
        self._old_tempdir = tempfile.tempdir
        self._old_env = {key: os.environ.get(key) for key in ("TMPDIR", "TEMP", "TMP")}

    def _remove(self, directory):
        # Никогда не обходим произвольные tmp*: проверяем границы перед rmtree.
        if directory.is_symlink() or directory.resolve().parent != self.root:
            raise ValueError("Temporary directory escaped application root")
        if not directory.name.startswith("worker-"):
            raise ValueError("Not an application worker directory")
        shutil.rmtree(directory)

    def _collect_locked(self):
        for directory in self.root.glob("worker-*"):
            if (
                directory == self.directory
                or directory.is_symlink()
                or not directory.is_dir()
            ):
                continue
            try:
                owner = _acquire(directory / ".owner.lock", blocking=False)
                if owner is None:
                    continue
                # На Windows открытый lock-файл нельзя удалить. Общий .gc.lock
                # исключает гонку со стартом другого воркера после закрытия owner.
                owner.close()
                self._remove(directory)
            except OSError:
                logger.warning(
                    "Не удалось убрать каталог завершённого воркера: %s",
                    directory,
                    exc_info=True,
                )

    def collect(self):
        """Удаляет аварийные остатки, не затрагивая живые воркеры."""
        with _guard(self.root):
            self._collect_locked()

    def start(self):
        """Убирает аварийные остатки и удерживает блокировку нового каталога."""
        if self.root.is_symlink():
            raise ValueError("Application temp root must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = self.root.resolve()
        with _guard(self.root):
            self._collect_locked()
            self.directory = self.root / ("worker-" + uuid.uuid4().hex)
            self.directory.mkdir(mode=0o700)
            self._owner = _acquire(self.directory / ".owner.lock")
        tempfile.tempdir = str(self.directory)
        # OCR, LibreOffice, ffmpeg и Chromium наследуют тот же каталог.
        for key in self._old_env:
            os.environ[key] = str(self.directory)
        atexit.register(self.close)
        return self

    def close(self):
        """Освобождает и удаляет собственный каталог при штатном завершении."""
        if self._owner is None:
            return
        with _guard(self.root):
            self._owner.close()
            self._owner = None
            try:
                self._remove(self.directory)
            except OSError:
                logger.warning(
                    "Каталог воркера будет удалён при следующей уборке: %s",
                    self.directory,
                    exc_info=True,
                )
        tempfile.tempdir = self._old_tempdir
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        atexit.unregister(self.close)
