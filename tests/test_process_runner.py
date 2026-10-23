import sys
from threading import Event

from al_media.core import process_runner
from al_media.core.process_runner import ProcessRunner


def test_tool_output_is_drained_and_exit_is_reported(qtbot):
    runner = ProcessRunner([sys.executable, "-c", "print('ready'); import sys; sys.stderr.write('diagnostic')"], "out")
    chunks = []
    runner.output.connect(lambda channel, data: chunks.append((channel, data)))
    with qtbot.waitSignal(runner.finished, timeout=5000) as result:
        runner.start()
    runner.wait()
    assert result.args == [0]
    output = b"".join(data for channel, data in chunks if channel == "out")
    assert b"ready" in output and b"diagnostic" in output


def test_cancellation_while_tool_is_still_launching(qtbot, monkeypatch):
    launch_entered, launch_allowed = Event(), Event()
    popen = process_runner.subprocess.Popen

    def delayed_launch(*args, **kwargs):
        launch_entered.set()
        if not launch_allowed.wait(3):
            raise OSError("Test launch was not released")
        return popen(*args, **kwargs)

    monkeypatch.setattr(process_runner.subprocess, "Popen", delayed_launch)
    runner = ProcessRunner([sys.executable, "-c", "import time; time.sleep(30)"], "out")
    with qtbot.waitSignal(runner.finished, timeout=5000) as result:
        runner.start()
        qtbot.waitUntil(launch_entered.is_set)
        runner.cancel()
        launch_allowed.set()
    runner.wait()
    assert result.args[0] != 0 and runner.process is None


def test_missing_tool_finishes_with_error(qtbot, tmp_path):
    runner = ProcessRunner([str(tmp_path / "missing.exe")], "out")
    output = []
    runner.output.connect(lambda _channel, data: output.append(data))
    with qtbot.waitSignal(runner.finished, timeout=5000) as result:
        runner.start()
    runner.wait()
    assert result.args == [1] and output
