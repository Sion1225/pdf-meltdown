"""백그라운드 파일 출력 작업 (저장/추출/분할 공용).

메인 스레드가 멈추지 않도록 QThreadPool 에서 실행하고, 진행률/완료/실패/취소를
시그널로 알린다. 실제 작업 내용은 job 함수로 주입한다:

    job(report, should_cancel) -> result
      report(done, total): 진행률 보고
      should_cancel() -> bool: True 면 중단
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from .core import CancelledError

Job = Callable[[Callable[[int, int], None], Callable[[], bool]], object]


class ExportSignals(QObject):
    progress = Signal(int, int)   # (done, total)
    finished = Signal(object)     # 작업 결과
    failed = Signal(str)          # 오류 메시지
    cancelled = Signal()


class ExportTask(QRunnable):
    def __init__(self, job: Job, signals: ExportSignals) -> None:
        super().__init__()
        self._job = job
        self.signals = signals
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = self._job(
                lambda d, t: self.signals.progress.emit(d, t),
                lambda: self._cancel,
            )
            self.signals.finished.emit(result)
        except CancelledError:
            self.signals.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(str(e))
