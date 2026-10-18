from PySide6.QtCore import QEventLoop, QTimer


def wait_for(predicate, timeout=60000):
    loop = QEventLoop()
    poll, deadline = QTimer(), QTimer()
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start(25)
    deadline.start(timeout)
    if not predicate():
        loop.exec()
    poll.stop()
    deadline.stop()
    if not predicate():
        raise RuntimeError("Timed out waiting for the queue")
