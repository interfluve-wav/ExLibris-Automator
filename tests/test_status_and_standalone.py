#!/usr/bin/env python3
"""Regression tests for standalone/status behavior in esp_gui_web.py."""

import json
import os
import tempfile
import threading
import unittest
from collections import deque

import esp_gui_web as gui


class DummyStandalone:
    """Minimal object to call StandaloneManager.add_citation without full init."""

    def __init__(self, config):
        self.lock = threading.Lock()
        self.queue = deque()
        self._config = config
        self.saved_stats = None

    def get_config(self):
        return self._config

    def save_config(self, updates):
        if "stats" in updates:
            self.saved_stats = updates["stats"]
        self._config.update(updates)


class TestStatusAndStandalone(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig = {
            "IS_STANDALONE": gui.IS_STANDALONE,
            "BOT_CONFIG_FILE": gui.BOT_CONFIG_FILE,
            "PROJECT_DIR": gui.PROJECT_DIR,
            "COMPLETION_STATUS_FILE": gui.COMPLETION_STATUS_FILE,
            "RUN_BASE_ENQUEUED": gui.RUN_BASE_ENQUEUED,
            "RUN_BASE_PROCESSED": gui.RUN_BASE_PROCESSED,
        }
        gui.IS_STANDALONE = False
        gui.PROJECT_DIR = self.tmp_dir.name
        gui.BOT_CONFIG_FILE = os.path.join(self.tmp_dir.name, "bot_config.json")
        gui.COMPLETION_STATUS_FILE = os.path.join(self.tmp_dir.name, "gui_completion_status.json")
        gui.RUN_BASE_ENQUEUED = None
        gui.RUN_BASE_PROCESSED = None

    def tearDown(self):
        gui.IS_STANDALONE = self.orig["IS_STANDALONE"]
        gui.BOT_CONFIG_FILE = self.orig["BOT_CONFIG_FILE"]
        gui.PROJECT_DIR = self.orig["PROJECT_DIR"]
        gui.COMPLETION_STATUS_FILE = self.orig["COMPLETION_STATUS_FILE"]
        gui.RUN_BASE_ENQUEUED = self.orig["RUN_BASE_ENQUEUED"]
        gui.RUN_BASE_PROCESSED = self.orig["RUN_BASE_PROCESSED"]
        self.tmp_dir.cleanup()

    def _write_bot_config(self, enqueued, processed, errors=0):
        payload = {
            "stats": {"enqueued": enqueued, "processed": processed, "errors": errors},
            "paused": False,
            "default_researcher": "Buck, John R",
            "asset_mode": "presentation",
            "additional_topics": {},
            "auto_fill_authors": True,
            "author_add_delay_ms": 1000,
            "auto_restart_interval": 0,
        }
        with open(gui.BOT_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def _write_completion(self, status, timestamp, error=None, queue_remaining=0):
        payload = {
            "status": status,
            "citation_id": "cid_1",
            "timestamp": timestamp,
            "queue_remaining": queue_remaining,
        }
        if error:
            payload["error"] = error
        with open(gui.COMPLETION_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_standalone_add_splitting_single_line_mode(self):
        cfg = {"asset_mode": "auto", "default_researcher": "Buck, John R", "stats": {"enqueued": 100}}
        dummy = DummyStandalone(cfg)
        text = (
            "Alpha citation long enough to pass validation threshold 12345\n"
            "Beta citation long enough to pass validation threshold 67890\n"
            "Gamma citation long enough to pass validation threshold abcde\n"
            "Delta citation long enough to pass validation threshold vwxyz"
        )
        result = gui.StandaloneManager.add_citation(dummy, text)
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 4)
        self.assertEqual(len(dummy.queue), 4)
        self.assertEqual(dummy.saved_stats["enqueued"], 104)

    def test_status_lifecycle_filling_completed_failed(self):
        self._write_bot_config(enqueued=10, processed=8)
        now = gui.time.time()

        self._write_completion("filling", now)
        status = gui.get_status_data()
        self.assertEqual(status["status"], "filling")
        self.assertIn("Filling", status["statusText"])

        self._write_completion("completed", now, queue_remaining=2)
        status = gui.get_status_data()
        self.assertEqual(status["status"], "completed")

        self._write_completion("failed", now, error="boom")
        status = gui.get_status_data()
        self.assertEqual(status["status"], "failed")
        self.assertIn("boom", status["statusText"])

    def test_queue_current_run_semantics(self):
        # Initial baseline snapshot for this run.
        self._write_bot_config(enqueued=1040, processed=1000)
        status1 = gui.get_status_data()
        self.assertEqual(status1["queueSize"], 0)

        # Add 4 this run => queue should be 4.
        self._write_bot_config(enqueued=1044, processed=1000)
        status2 = gui.get_status_data()
        self.assertEqual(status2["queueSize"], 4)

        # Process one => queue should go down to 3.
        self._write_bot_config(enqueued=1044, processed=1001)
        status3 = gui.get_status_data()
        self.assertEqual(status3["queueSize"], 3)

    def test_stale_filling_timeout_recovery(self):
        self._write_bot_config(enqueued=3, processed=0)
        stale_ts = gui.time.time() - (gui.FILLING_STATUS_STALE_SEC + 5)
        self._write_completion("filling", stale_ts)

        status = gui.get_status_data()
        # Should recover from stale filling and stop reporting "filling".
        self.assertNotEqual(status["status"], "filling")
        self.assertFalse(os.path.exists(gui.COMPLETION_STATUS_FILE))


if __name__ == "__main__":
    unittest.main()
