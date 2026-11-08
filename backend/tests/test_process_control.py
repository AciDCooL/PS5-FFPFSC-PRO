from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from process_control import (
    get_process_children,
    suspend_process_tree,
    resume_process_tree,
    check_storage_accessible,
)


class TestProcessControl(unittest.TestCase):
    def test_suspend_and_resume_process(self):
        # Spawn a worker process that continuously increments an integer in a file
        with tempfile.TemporaryDirectory() as tmpdir:
            counter_file = Path(tmpdir) / "counter.txt"
            counter_file.write_text("0", encoding="utf-8")

            worker_code = f"""
import time
from pathlib import Path
f = Path(r'{counter_file}')
count = 0
while True:
    count += 1
    f.write_text(str(count), encoding='utf-8')
    time.sleep(0.05)
"""
            proc = subprocess.Popen([sys.executable, "-c", worker_code])
            try:
                # Wait for process to start counting
                time.sleep(0.2)
                val_start = int(counter_file.read_text(encoding="utf-8").strip() or 0)
                self.assertGreater(val_start, 0)

                # Suspend process
                ok_suspend = suspend_process_tree(proc.pid)
                self.assertTrue(ok_suspend, "Process suspension failed")

                val_after_suspend = int(counter_file.read_text(encoding="utf-8").strip() or 0)
                # Wait while suspended
                time.sleep(0.3)
                val_while_suspended = int(counter_file.read_text(encoding="utf-8").strip() or 0)
                self.assertEqual(
                    val_after_suspend,
                    val_while_suspended,
                    "Process continued executing while suspended!"
                )

                # Resume process
                ok_resume = resume_process_tree(proc.pid)
                self.assertTrue(ok_resume, "Process resumption failed")

                time.sleep(0.2)
                val_after_resume = int(counter_file.read_text(encoding="utf-8").strip() or 0)
                self.assertGreater(
                    val_after_resume,
                    val_while_suspended,
                    "Process did not resume execution!"
                )
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def test_check_storage_accessible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ok, fail = check_storage_accessible([tmp_path], timeout=0.5)
            self.assertTrue(ok)
            self.assertIsNone(fail)

            # Test nonexistent path
            missing = tmp_path / "nonexistent_folder" / "sub" / "file.txt"
            ok2, fail2 = check_storage_accessible([missing], timeout=0.2)
            self.assertFalse(ok2)
            self.assertEqual(fail2, str(missing))


    def test_queue_engine_pause_resume(self):
        from core import QueueEngine
        engine = QueueEngine()
        # Not running -> pause should fail
        ok, msg = engine.pause_queue()
        self.assertFalse(ok)

        # Start dummy process
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        try:
            engine.is_running = True
            engine._active_extract_proc = proc
            ok_pause, _ = engine.pause_queue()
            self.assertTrue(ok_pause)
            self.assertTrue(engine.is_paused)
            self.assertTrue(engine.status["is_paused"])

            ok_resume, _ = engine.resume_queue()
            self.assertTrue(ok_resume)
            self.assertFalse(engine.is_paused)
            self.assertFalse(engine.status["is_paused"])
            self.assertGreaterEqual(engine._total_paused_duration, 0.0)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
