import subprocess
import sys
from pathlib import Path

from meridian.lib.install.lock import state_lock

_LOCK_PROBE = """
import fcntl
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a+b") as handle:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(2)
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
raise SystemExit(0)
"""


def test_state_lock_acquires_and_releases_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / ".meridian" / "agents.lock"
    flock_path = lock_path.with_name("agents.lock.flock")

    with state_lock(lock_path):
        assert flock_path.exists()
        held = subprocess.run(
            [sys.executable, "-c", _LOCK_PROBE, str(flock_path)],
            check=False,
        )
        assert held.returncode == 2

    released = subprocess.run(
        [sys.executable, "-c", _LOCK_PROBE, str(flock_path)],
        check=False,
    )
    assert released.returncode == 0
