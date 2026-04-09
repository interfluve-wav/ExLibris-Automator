"""
Minimal stdout logger with timestamps and levels (DEBUG, INFO, WARN, ERROR).
Used by the Discord bot and automation worker.
"""
import sys
import os
import datetime as _dt


_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
_DEFAULT_LEVEL = _LEVELS.get(os.getenv("LOG_LEVEL", "INFO").upper(), 20)


class _Logger:
    def __init__(self, section: str):
        self.section = section

    def _ts(self) -> str:
        return _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _should(self, level: str) -> bool:
        return _LEVELS.get(level, 20) >= _DEFAULT_LEVEL

    def _out(self, level: str, msg: str):
        if not self._should(level):
            return
        sys.stdout.write(f"[{self._ts()}] [{self.section}] [{level}] {msg}\n")
        sys.stdout.flush()

    def info(self, msg: str):
        self._out('INFO', msg)

    def warn(self, msg: str):
        self._out('WARN', msg)

    def error(self, msg: str):
        self._out('ERROR', msg)

    def debug(self, msg: str):
        self._out('DEBUG', msg)


def make_logger(section: str) -> _Logger:
    return _Logger(section)


