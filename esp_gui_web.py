#!/usr/bin/env python3
"""
Web-based GUI launcher for ESP Citation Bot
Runs a Flask web server with a web interface
"""

import os
import json
import time
import threading
import webbrowser
import subprocess
from flask import Flask, render_template, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename
import PyPDF2
import docx
import pandas as pd
import io
import re
import string
import sys
import argparse
from collections import deque
from rapidfuzz import fuzz

# Load environment variables from .env file
from dotenv import load_dotenv
from utils.asset_type_utils import normalize_config_mode
from utils.config_manager import get_config_manager
from utils.input_validation import validate_citation_text, sanitize_text
load_dotenv()

# Get project directory from script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = SCRIPT_DIR

CONTROL_FILL = os.path.join(PROJECT_DIR, "fill_next_signal")
CONTROL_SHUTDOWN = os.path.join(PROJECT_DIR, "shutdown_signal")
ADD_CITATION_FILE = os.path.join(PROJECT_DIR, "gui_add_citation.json")
CONTROL_GO_HOME = os.path.join(PROJECT_DIR, "gui_go_home.json")
CONTROL_CONTINUE = os.path.join(PROJECT_DIR, "gui_continue.json")
COMPLETION_STATUS_FILE = os.path.join(PROJECT_DIR, "gui_completion_status.json")
COMPLETED_STATUS_TTL_SEC = 5
FAILED_STATUS_TTL_SEC = 10
FILLING_STATUS_STALE_SEC = 120

# Try to find bot_config.json
BOT_CONFIG_PATH = os.getenv('BOT_CONFIG_PATH', os.path.join(PROJECT_DIR, "bot_config.json"))
BOT_CONFIG_FILE = BOT_CONFIG_PATH if os.path.exists(BOT_CONFIG_PATH) else os.path.join(PROJECT_DIR, "bot_config.json")

# Get channel ID from environment
CITATION_CHANNEL_ID = os.getenv('CITATION_CHANNEL_ID')
if not CITATION_CHANNEL_ID:
    print("⚠️  Warning: CITATION_CHANNEL_ID not set in environment or .env file")
    print("💡 Some features (like 'Add Citation' and 'Fill Next') may not work properly")

app = Flask(__name__, template_folder='templates')

# Global Standalone Manager instance
standalone_manager = None
IS_STANDALONE = False
# Baseline snapshot for "current run" queue display in bot mode.
RUN_BASE_ENQUEUED = None
RUN_BASE_PROCESSED = None


def split_citation_blocks(text: str) -> list[str]:
    """
    Split bulk input into citations.

    Rules:
    - Blank lines separate citations (paragraph blocks).
    - Single wrapped newlines within a paragraph are preserved as one citation.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    # Primary split on blank lines only.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    if len(blocks) > 1:
        return [' '.join(b.split()) for b in blocks if b.strip()]

    # No blank-line delimiters: treat as one citation, normalize whitespace.
    return [' '.join(raw.split())]

class StandaloneManager:
    """
    Manages the citation queue and worker process directly (Standalone Mode).
    Replaces the need for the Discord bot.
    """
    def __init__(self):
        # Use configured channel ID if available to share topics/config with bot mode,
        # otherwise fallback to 'local'
        self.channel_id = CITATION_CHANNEL_ID if CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.strip() else "local"
        self.queue = deque()
        self.processing_citation = None
        self.active_process = None
        self.process_fill_count = 0
        self.control_file = os.path.join(PROJECT_DIR, f"citation_control_{self.channel_id}.json")
        self.status_file = os.path.join(PROJECT_DIR, f"citation_status_{self.channel_id}.json")
        self.config_manager = get_config_manager()
        self.config_manager.initialize(BOT_CONFIG_FILE, default_factory=self._default_config)
        self.lock = threading.Lock()

        # Force unpause on startup (fix for "Bot is paused" error from previous sessions)
        self.save_config({'paused': False})

        # Start background monitor
        threading.Thread(target=self._monitor_status, daemon=True).start()
        print(f"🚀 Standalone Manager initialized (Channel: {self.channel_id})")

    def _default_config(self):
        return {
            "default_researcher": os.getenv("DEFAULT_RESEARCHER", "Scarano, Frank J"),
            "asset_mode": "auto",
            "paused": False,
            "auto_restart_interval": 0,
            "stats": {"enqueued": 0, "processed": 0, "errors": 0},
            "additional_topics": {}
        }

    def get_config(self):
        return self.config_manager.get_all_sync()

    def save_config(self, updates):
        self.config_manager.update_sync(updates)
        self.config_manager.save_sync()

    def add_citation(self, text):
        if not text:
            return {'success': False, 'error': 'No text'}

        count = 0
        # Keep wrapped citation lines together unless separated by blank lines.
        lines = split_citation_blocks(text)
        if not lines:
            lines = [text.strip()]

        with self.lock:
            config = self.get_config()
            for line in lines:
                # Basic validation
                valid, msg = validate_citation_text(line)
                if not valid:
                    continue

                # Determine asset type (simplified logic)
                asset_type = config.get('asset_mode', 'auto')
                if 'poster' in line.lower() and asset_type == 'auto':
                    asset_type = 'poster'
                elif asset_type == 'auto':
                    asset_type = 'presentation'

                citation = {
                    'text': sanitize_text(line),
                    'asset_type': asset_type,
                    'citation_id': f"local_{int(time.time()*1000)}_{count}",
                    'researcher': config.get('default_researcher')
                }
                self.queue.append(citation)
                count += 1

            # Update stats
            stats = config.get('stats', {'enqueued': 0})
            stats['enqueued'] = stats.get('enqueued', 0) + count
            self.save_config({'stats': stats})

        return {'success': True, 'count': count}

    def trigger_fill(self):
        with self.lock:
            config = self.get_config()
            if config.get('paused'):
                return {'success': False, 'error': 'Bot is paused'}

            if self.processing_citation is not None:
                return {'success': False, 'error': 'Already processing a citation'}

            if not self.queue:
                return {'success': False, 'error': 'Queue is empty'}

            # Auto-restart check (PRE-CHECK logic)
            restart_interval = config.get('auto_restart_interval', 0)
            if restart_interval > 0 and self.process_fill_count >= restart_interval:
                print(f"🔄 Auto-restart: {self.process_fill_count}/{restart_interval} fills. Restarting worker...")
                self._stop_worker()
                self.process_fill_count = 0

            # Start worker if needed
            self._ensure_worker_running()

            # Pop and process
            citation = self.queue.popleft()
            self.processing_citation = citation

            # Write control file
            data = {
                'text': citation['text'],
                'asset_type': citation['asset_type'],
                'citation_id': citation['citation_id'],
                'researcher': config.get('default_researcher'),
                'channel_id': self.channel_id
            }
            with open(self.control_file, 'w') as f:
                json.dump(data, f)

            # Write filling status for UI
            with open(COMPLETION_STATUS_FILE, 'w') as f:
                json.dump({
                    'status': 'filling',
                    'citation_id': citation['citation_id'],
                    'timestamp': time.time()
                }, f)

        return {'success': True}

    def _ensure_worker_running(self):
        if self.active_process and self.active_process.poll() is None:
            return

        # Wait for Xvfb display socket to be ready before launching headed browser
        display = ':99'
        socket_path = '/tmp/.X11-unix/X99'
        for i in range(20):
            if os.path.exists(socket_path):
                break
            print(f"⏳ Waiting for Xvfb display {display} ({i+1}/20)...")
            time.sleep(1)
        else:
            print(f"⚠️  Xvfb socket not found at {socket_path} — worker may fail. Is VNC Desktop running?")

        print(f"🚀 Starting standalone worker for channel '{self.channel_id}'...")
        cmd = [sys.executable, '-m', 'automation.worker', self.channel_id]
        worker_env = os.environ.copy()
        if not worker_env.get('DISPLAY'):
            worker_env['DISPLAY'] = display
        self.active_process = subprocess.Popen(cmd, cwd=PROJECT_DIR, env=worker_env)
        # Give it a moment to init
        time.sleep(2)

    def _stop_worker(self):
        if self.active_process:
            try:
                self.active_process.terminate()
                self.active_process.wait(timeout=2)
            except:
                self.active_process.kill()
            self.active_process = None

    def close(self):
        self._stop_worker()
        # Clean up files
        for f in [self.control_file, self.status_file]:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

    def _monitor_status(self):
        last_id = None
        while True:
            try:
                if os.path.exists(self.status_file):
                    with open(self.status_file, 'r') as f:
                        status = json.load(f)

                    written_id = status.get('last_written_id')
                    state = status.get('state')
                    if written_id and written_id != last_id and state == 'completed':
                        # Completed a citation
                        last_id = written_id
                        with self.lock:
                            stats = self.get_config().get('stats', {})
                            stats['processed'] = stats.get('processed', 0) + 1
                            self.save_config({'stats': stats})
                            if self.processing_citation and self.processing_citation.get('citation_id') == written_id:
                                self.processing_citation = None
                            self.process_fill_count += 1
                        with open(COMPLETION_STATUS_FILE, 'w') as f:
                            json.dump({
                                'status': 'completed',
                                'citation_id': written_id,
                                'timestamp': time.time(),
                                'queue_remaining': len(self.queue)
                            }, f)
                    elif written_id and written_id != last_id and state == 'failed':
                        last_id = written_id
                        with self.lock:
                            stats = self.get_config().get('stats', {})
                            stats['errors'] = stats.get('errors', 0) + 1
                            self.save_config({'stats': stats})
                            if self.processing_citation and self.processing_citation.get('citation_id') == written_id:
                                self.processing_citation = None
                            self.process_fill_count += 1
                        with open(COMPLETION_STATUS_FILE, 'w') as f:
                            json.dump({
                                'status': 'failed',
                                'citation_id': written_id,
                                'timestamp': time.time(),
                                'error': status.get('error') or 'Citation processing failed',
                                'queue_remaining': len(self.queue)
                            }, f)
            except Exception:
                pass
            time.sleep(1)

    def get_status_dict(self):
        config = self.get_config()
        stats = config.get('stats', {})
        processed = stats.get('processed', 0)
        enqueued = stats.get('enqueued', 0)
        errors = stats.get('errors', 0)

        # Resume-style estimated time saved based on documented speed improvements.
        # NOTE: This is an estimate (not exact measured runtime), meant for resume quantification.
        time_saved_estimate_label = "-"
        try:
            _after_s = 0.5  # target parsing/processing time reference
            _speedup_min = 0.30
            _speedup_max = 0.50
            _saved_min_per = _after_s * _speedup_min / (1 - _speedup_min)
            _saved_max_per = _after_s * _speedup_max / (1 - _speedup_max)
            _saved_min = processed * _saved_min_per
            _saved_max = processed * _saved_max_per

            def _fmt_s(sec: float) -> str:
                if sec < 60:
                    return f"{sec:.1f}s"
                if sec < 3600:
                    return f"{sec/60:.1f}m"
                return f"{sec/3600:.2f}h"

            time_saved_estimate_label = f"{_fmt_s(_saved_min)} - {_fmt_s(_saved_max)}"
        except Exception:
            pass

        return {
            'status': 'ready' if self.queue else 'idle', # simplified
            'statusText': 'Ready' if self.queue else 'Waiting...',
            'queueSize': len(self.queue),
            'processed': processed,
            'enqueued': enqueued,
            'errors': errors,
            'citationChannelId': self.channel_id,
            'paused': config.get('paused', False),
            'researcher': config.get('default_researcher', '-'),
            'assetMode': config.get('asset_mode', 'auto'),
            'additionalTopics': config.get('additional_topics', {}).get(self.channel_id, []),
            'autoFillAuthors': config.get('auto_fill_authors', True),
            'authorAddDelayMs': config.get('author_add_delay_ms', 1000),
            'autoRestartInterval': config.get('auto_restart_interval', 0),

            # Resume-style stats
            'timeSavedEstimateLabel': time_saved_estimate_label,
        }

# --- Helper Functions ---

def get_status_data():
    """Get current status"""
    global RUN_BASE_ENQUEUED, RUN_BASE_PROCESSED
    if IS_STANDALONE and standalone_manager:
        # Mix in the completion status file logic if needed, or let manager handle it
        # The manager writes to COMPLETION_STATUS_FILE so the frontend logic below
        # (reading that file) will still work for 'filling'/'completed' states.
        # We just need to base the config/queue data on the manager.
        base = standalone_manager.get_status_dict()

        # Overlay completion status from file (shared logic with hybrid mode)
        if os.path.exists(COMPLETION_STATUS_FILE):
            try:
                with open(COMPLETION_STATUS_FILE, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                file_status = status_data.get('status', 'idle')
                file_timestamp = status_data.get('timestamp', 0)
                age = time.time() - file_timestamp
                if file_status == 'completed':
                    if age < COMPLETED_STATUS_TTL_SEC:
                        base['status'] = 'completed'
                        base['statusText'] = '✅ Done! Ready for next.'
                    else:
                        try:
                            os.remove(COMPLETION_STATUS_FILE)
                        except Exception:
                            pass
                elif file_status == 'failed':
                    if age < FAILED_STATUS_TTL_SEC:
                        base['status'] = 'failed'
                        base['statusText'] = f"❌ Fill failed: {status_data.get('error', 'Citation processing failed')}"
                    else:
                        try:
                            os.remove(COMPLETION_STATUS_FILE)
                        except Exception:
                            pass
                elif file_status == 'filling':
                    if age < FILLING_STATUS_STALE_SEC:
                        base['status'] = 'filling'
                        base['statusText'] = 'Status: Filling citation...'
                    else:
                        # Stale filling marker (worker crash or interrupted session)
                        try:
                            os.remove(COMPLETION_STATUS_FILE)
                        except Exception:
                            pass
            except: pass

        if base['status'] == 'idle' and base['queueSize'] > 0:
            base['status'] = 'ready'
            base['statusText'] = 'Status: Ready to fill next citation'

        return base

    try:
        status = 'idle'
        status_text = 'Status: Waiting for citations...'
        queue_size = 0
        processed = 0
        enqueued = 0

        # Check completion status
        if os.path.exists(COMPLETION_STATUS_FILE):
            try:
                with open(COMPLETION_STATUS_FILE, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                file_status = status_data.get('status', 'idle')
                file_timestamp = status_data.get('timestamp', 0)

                # Only show completed status for 5 seconds after completion
                time_since_completion = time.time() - file_timestamp

                if file_status == 'completed':
                    if time_since_completion < COMPLETED_STATUS_TTL_SEC:
                        status = 'completed'
                        queue_remaining = status_data.get('queue_remaining', 0)
                        if queue_remaining > 0:
                            status_text = f'✅ Done! Ready for next citation. ({queue_remaining} remaining)'
                        else:
                            status_text = '✅ All citations completed!'
                    else:
                        # Completed status has expired, clean up the file
                        try:
                            os.remove(COMPLETION_STATUS_FILE)
                        except Exception:
                            pass
                elif file_status == 'filling':
                    if time_since_completion < FILLING_STATUS_STALE_SEC:
                        status = 'filling'
                        status_text = 'Status: Filling citation...'
                    else:
                        try:
                            os.remove(COMPLETION_STATUS_FILE)
                        except Exception:
                            pass
                elif file_status == 'failed':
                    if time_since_completion < FAILED_STATUS_TTL_SEC:
                        status = 'failed'
                        status_text = f"❌ Fill failed: {status_data.get('error', 'Citation processing failed')}"
                    else:
                        try:
                            os.remove(COMPLETION_STATUS_FILE)
                        except Exception:
                            pass
            except Exception:
                pass

        # Get queue info
        config_files = [
            BOT_CONFIG_FILE,
            os.path.join(PROJECT_DIR, "bot_config.json"),
        ]

        config = {}
        stats = {}
        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    stats = config.get('stats', {})
                    enqueued = stats.get('enqueued', 0)
                    processed = stats.get('processed', 0)
                    # Show queue for current app run (not lifetime totals).
                    if RUN_BASE_ENQUEUED is None or RUN_BASE_PROCESSED is None:
                        RUN_BASE_ENQUEUED = enqueued
                        RUN_BASE_PROCESSED = processed
                    # If counters reset underneath us, re-baseline.
                    if enqueued < RUN_BASE_ENQUEUED or processed < RUN_BASE_PROCESSED:
                        RUN_BASE_ENQUEUED = enqueued
                        RUN_BASE_PROCESSED = processed
                    run_enqueued = max(0, enqueued - RUN_BASE_ENQUEUED)
                    run_processed = max(0, processed - RUN_BASE_PROCESSED)
                    queue_size = max(0, run_enqueued - run_processed)
                    break
                except Exception:
                    continue

        # Determine status if not set by completion file
        if status == 'idle' and queue_size > 0:
            status = 'ready'
            status_text = 'Status: Ready to fill next citation'

        # Get additional stats
        paused = config.get('paused', False) if config else False
        researcher = config.get('default_researcher', '-') if config else '-'
        asset_mode = config.get('asset_mode', '-') if config else '-'
        errors = stats.get('errors', 0) if config else 0

        # Get additional topics for current channel
        additional_topics = []
        if config and CITATION_CHANNEL_ID and CITATION_CHANNEL_ID.isdigit():
            topics_by_channel = config.get('additional_topics', {})
            additional_topics = topics_by_channel.get(str(CITATION_CHANNEL_ID), [])

        # Get auto-fill authors setting (default to True for backward compatibility)
        auto_fill_authors = config.get('auto_fill_authors', True) if config else True
        author_add_delay_ms = config.get('author_add_delay_ms', 1000) if config else 1000
        auto_restart_interval = config.get('auto_restart_interval', 0) if config else 0

        # Resume-style estimate: based on documented ~30-50% faster processing
        # and a current parser target of ~0.5s per citation.
        time_saved_estimate_label = "-"
        try:
            _after_s = 0.5
            _speedup_min = 0.30
            _speedup_max = 0.50
            _saved_min_per = _after_s * _speedup_min / (1 - _speedup_min)
            _saved_max_per = _after_s * _speedup_max / (1 - _speedup_max)
            _saved_min = processed * _saved_min_per
            _saved_max = processed * _saved_max_per

            def _fmt_s(sec: float) -> str:
                if sec < 60:
                    return f"{sec:.1f}s"
                if sec < 3600:
                    return f"{sec/60:.1f}m"
                return f"{sec/3600:.2f}h"

            time_saved_estimate_label = f"{_fmt_s(_saved_min)} - {_fmt_s(_saved_max)}"
        except Exception:
            pass

        return {
            'status': status,
            'statusText': status_text,
            'queueSize': queue_size,
            'processed': processed,
            'enqueued': enqueued,
            'errors': errors,
            'citationChannelId': CITATION_CHANNEL_ID or '-',
            'paused': paused,
            'researcher': researcher,
            'assetMode': asset_mode,
            'additionalTopics': additional_topics,
            'autoFillAuthors': auto_fill_authors,
            'authorAddDelayMs': author_add_delay_ms,
            'autoRestartInterval': auto_restart_interval,

            # Resume-style stats
            'timeSavedEstimateLabel': time_saved_estimate_label,
        }
    except Exception as e:
        return {
            'status': 'idle',
            'statusText': f'Error: {str(e)}',
            'queueSize': 0,
            'processed': 0,
            'enqueued': 0
        }

def add_citation_to_queue(text):
    """Add citation to queue"""
    if not text:
        return {'success': False, 'error': 'No citation text provided'}

    try:
        # Keep wrapped citation lines together unless separated by blank lines.
        citations = split_citation_blocks(text)
        if not citations:
            citations = [text]

        added_count = 0
        for citation in citations:
            try:
                with open(ADD_CITATION_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'text': citation}, f)

                # Wait for bot to process
                max_wait = 5
                waited = 0
                while waited < max_wait:
                    time.sleep(0.2)
                    waited += 0.2
                    try:
                        with open(ADD_CITATION_FILE, 'r', encoding='utf-8') as f:
                            result = json.load(f)
                        if result.get('success'):
                            added_count += 1
                            break
                        elif 'error' in result:
                            return {'success': False, 'error': result.get('error', 'Unknown error')}
                    except (json.JSONDecodeError, FileNotFoundError):
                        continue

                time.sleep(0.1)
            except Exception as e:
                return {'success': False, 'error': str(e)}

        return {'success': True, 'count': added_count}
    except Exception as e:
        return {'success': False, 'error': str(e)}


DISCORD_BOT_LOG_PATH = os.path.join(PROJECT_DIR, "logs", "discord_bot.log")
_LOG_TAIL_BYTES = 400_000
_LOG_MAX_LINES = 600
_WORKER_MARKER = " [WORKER] "


def _tail_log_lines(path: str) -> list:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk = min(size, _LOG_TAIL_BYTES)
            f.seek(-chunk, os.SEEK_END)
            raw = f.read().decode("utf-8", errors="replace")
        return raw.splitlines()
    except OSError:
        return []


def _logs_payload(kind: str) -> dict:
    """kind: 'discord' (bot process, excludes worker-tagged lines) or 'worker' ([WORKER] only)."""
    lines = _tail_log_lines(DISCORD_BOT_LOG_PATH)
    if kind == "worker":
        filtered = [ln for ln in lines if _WORKER_MARKER in ln]
    else:
        filtered = [ln for ln in lines if _WORKER_MARKER not in ln]
    if len(filtered) > _LOG_MAX_LINES:
        filtered = filtered[-_LOG_MAX_LINES:]
    text = "\n".join(filtered)
    hint = None
    if not os.path.isfile(DISCORD_BOT_LOG_PATH):
        hint = (
            "No logs/discord_bot.log yet. Run ./start_all.sh (or redirect the Discord bot’s stdout/stderr "
            "to logs/discord_bot.log) so bot and worker output is captured."
        )
    elif not text.strip():
        hint = (
            "No matching lines in the latest portion of the log. "
            + (
                "Worker messages use the [WORKER] tag from the automation process."
                if kind == "worker"
                else "This view hides [WORKER] lines; those appear under Citation Filler."
            )
        )
    return {
        "ok": True,
        "kind": kind,
        "text": text,
        "hint": hint,
        "source": "logs/discord_bot.log",
    }


# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/matcher')
def matcher():
    return render_template('matcher.html')


@app.route('/api/logs')
def api_logs():
    kind = (request.args.get("kind") or "discord").strip().lower()
    if kind not in ("discord", "worker"):
        return jsonify({"ok": False, "error": "kind must be discord or worker"}), 400
    return jsonify(_logs_payload(kind))


@app.route('/api/status')
def api_status():
    return jsonify(get_status_data())

@app.route('/api/add', methods=['POST'])
def api_add():
    data = request.json
    if IS_STANDALONE:
        return jsonify(standalone_manager.add_citation(data.get('text', '')))

    result = add_citation_to_queue(data.get('text', ''))
    return jsonify(result)

@app.route('/api/fill', methods=['POST'])
def api_fill():
    if IS_STANDALONE:
        return jsonify(standalone_manager.trigger_fill())

    try:
        with open(CONTROL_FILL, 'w') as f:
            f.write("1")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/close', methods=['POST'])
def api_close():
    if IS_STANDALONE:
        standalone_manager.close()
        def delayed_shutdown():
            time.sleep(1)
            os._exit(0)
        threading.Thread(target=delayed_shutdown, daemon=True).start()
        return jsonify({'success': True})

    try:
        with open(CONTROL_SHUTDOWN, 'w') as f:
            f.write("1")

        # Schedule server shutdown
        def delayed_shutdown():
            time.sleep(1)
            os._exit(0)

        threading.Thread(target=delayed_shutdown, daemon=True).start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/queue')
def api_queue():
    if IS_STANDALONE:
        q = list(standalone_manager.queue)
        items = []
        for i, c in enumerate(q, 1):
            items.append({
                'position': i,
                'text': c['text'][:100],
                'asset_type': c['asset_type'],
                'citation_id': c['citation_id']
            })
        return jsonify({'success': True, 'queue': items, 'count': len(items)})

    try:
        # Read queue via control file (bot will write it)
        queue_file = os.path.join(PROJECT_DIR, 'gui_queue.json')

        # Request queue from bot by creating a request file
        request_file = os.path.join(PROJECT_DIR, 'gui_queue_request.json')
        with open(request_file, 'w') as f:
            json.dump({'request': True, 'timestamp': time.time()}, f)

        # Wait for bot to respond (up to 2 seconds)
        max_wait = 2
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            if os.path.exists(queue_file):
                try:
                    with open(queue_file, 'r', encoding='utf-8') as f:
                        queue_data = json.load(f)
                    # Clean up
                    try:
                        os.remove(queue_file)
                        os.remove(request_file)
                    except Exception:
                        pass
                    return jsonify(queue_data)
                except (json.JSONDecodeError, FileNotFoundError):
                    continue

        # Clean up request file
        try:
            os.remove(request_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for queue data', 'queue': []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'queue': []})

@app.route('/api/clear', methods=['POST'])
def api_clear():
    if IS_STANDALONE:
        count = len(standalone_manager.queue)
        standalone_manager.queue.clear()
        return jsonify({'success': True, 'cleared': count})

    try:
        clear_file = os.path.join(PROJECT_DIR, 'gui_clear_queue.json')
        with open(clear_file, 'w') as f:
            json.dump({'clear': True, 'timestamp': time.time()}, f)

        # Wait for confirmation
        max_wait = 2
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(clear_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if result.get('success') is not None:
                    os.remove(clear_file)
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError):
                continue

        return jsonify({'success': True, 'message': 'Clear request sent'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/pause', methods=['POST'])
def api_pause():
    if IS_STANDALONE:
        standalone_manager.save_config({'paused': True})
        return jsonify({'success': True})
    try:
        pause_file = os.path.join(PROJECT_DIR, 'gui_pause.json')
        with open(pause_file, 'w') as f:
            json.dump({'pause': True, 'timestamp': time.time()}, f)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/resume', methods=['POST'])
def api_resume():
    if IS_STANDALONE:
        standalone_manager.save_config({'paused': False})
        return jsonify({'success': True})
    try:
        resume_file = os.path.join(PROJECT_DIR, 'gui_resume.json')
        with open(resume_file, 'w') as f:
            json.dump({'resume': True, 'timestamp': time.time()}, f)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/skip', methods=['POST'])
def api_skip():
    if IS_STANDALONE:
        standalone_manager.processing_citation = None
        return jsonify({'success': True, 'message': 'Skipped (local)'})
    try:
        skip_file = os.path.join(PROJECT_DIR, 'gui_skip.json')
        # Clear any existing file first
        if os.path.exists(skip_file):
            try:
                os.remove(skip_file)
            except Exception:
                pass

        with open(skip_file, 'w') as f:
            json.dump({'skip': True, 'timestamp': time.time()}, f)

        # Wait for bot to process and write response
        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(skip_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if result.get('success') is not None:
                    # Clean up
                    try:
                        os.remove(skip_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        # Clean up if no response
        try:
            os.remove(skip_file)
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Skip request sent'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/continue', methods=['POST'])
def api_continue():
    try:
        if os.path.exists(CONTROL_CONTINUE):
            os.remove(CONTROL_CONTINUE)
        with open(CONTROL_CONTINUE, 'w') as f:
            json.dump({'continue': True, 'timestamp': time.time()}, f)
        return jsonify({'success': True, 'message': 'Continue signal sent'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/go_home', methods=['POST'])
def api_go_home():
    try:
        if os.path.exists(CONTROL_GO_HOME):
            os.remove(CONTROL_GO_HOME)
        with open(CONTROL_GO_HOME, 'w') as f:
            json.dump({'go_home': True, 'timestamp': time.time()}, f)
        return jsonify({'success': True, 'message': 'Go home command sent'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/set_researcher', methods=['POST'])
def api_set_researcher():
    data = request.json
    researcher = data.get('researcher', '').strip()
    if not researcher: return jsonify({'success': False, 'error': 'Required'})

    if IS_STANDALONE:
        standalone_manager.save_config({'default_researcher': researcher})
        return jsonify({'success': True, 'researcher': researcher})

    try:
        researcher_file = os.path.join(PROJECT_DIR, 'gui_set_researcher.json')

        # Clear any existing file first
        if os.path.exists(researcher_file):
            try:
                os.remove(researcher_file)
            except Exception:
                pass

        # Write request
        with open(researcher_file, 'w', encoding='utf-8') as f:
            json.dump({'researcher': researcher, 'timestamp': time.time()}, f)

        # Wait for bot to process and write response (longer wait for config save)
        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(researcher_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                # Check if bot has written a response (has 'success' key)
                if 'success' in result:
                    # Clean up
                    try:
                        os.remove(researcher_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        # Clean up if no response
        try:
            os.remove(researcher_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/set_asset_type', methods=['POST'])
def api_set_asset_type():
    data = request.json
    asset_type = data.get('asset_type', '').strip()
    if not asset_type: return jsonify({'success': False, 'error': 'Required'})

    normalized = normalize_config_mode(asset_type)
    if IS_STANDALONE:
        standalone_manager.save_config({'asset_mode': normalized})
        return jsonify({'success': True, 'asset_type': normalized})

    try:
        # Normalize using shared utility
        normalized_type = normalize_config_mode(asset_type)

        asset_type_file = os.path.join(PROJECT_DIR, 'gui_set_asset_type.json')

        # Clear any existing file first
        if os.path.exists(asset_type_file):
            try:
                os.remove(asset_type_file)
            except Exception:
                pass

        # Write request with normalized type
        with open(asset_type_file, 'w', encoding='utf-8') as f:
            json.dump({'asset_type': normalized_type}, f)

        # Wait for bot response (polling)
        max_wait = 5  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                if os.path.exists(asset_type_file):
                    with open(asset_type_file, 'r', encoding='utf-8') as f:
                        response = json.load(f)
                    if 'success' in response:
                        return jsonify(response)
            except Exception:
                pass
            time.sleep(0.2)

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/set_author_add_delay', methods=['POST'])
def api_set_author_add_delay():
    data = request.json
    try:
        delay = int(data.get('delay_ms', 1000))
        if IS_STANDALONE:
            standalone_manager.save_config({'author_add_delay_ms': delay})
            return jsonify({'success': True})
    except: pass # fallthrough

    try:
        delay_ms = int(data.get('delay_ms', 1000))
        if delay_ms not in (500, 1000, 2000, 3000):
            return jsonify({'success': False, 'error': 'Delay must be 500, 1000, 2000, or 3000 ms'})

        control_file = os.path.join(PROJECT_DIR, 'gui_set_author_add_delay.json')

        # Clear existing
        if os.path.exists(control_file):
            try:
                os.remove(control_file)
            except Exception:
                pass

        # Write request
        with open(control_file, 'w', encoding='utf-8') as f:
            json.dump({'delay_ms': delay_ms, 'timestamp': time.time()}, f)

        # Wait for bot response
        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(control_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if 'success' in result:
                    try:
                        os.remove(control_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        try:
            os.remove(control_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid delay value'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/set_restart_policy', methods=['POST'])
def api_set_restart_policy():
    data = request.json
    try:
        enabled = data.get('enabled', False)
        interval = int(data.get('interval', 0))
        final = interval if enabled else 0

        if IS_STANDALONE:
            standalone_manager.save_config({'auto_restart_interval': final})
            return jsonify({'success': True})
    except: pass

    try:
        enabled = data.get('enabled', False)
        interval = int(data.get('interval', 0))

        # If disabled, set interval to 0
        final_interval = interval if enabled else 0

        control_file = os.path.join(PROJECT_DIR, 'gui_set_restart_policy.json')

        if os.path.exists(control_file):
            try:
                os.remove(control_file)
            except Exception:
                pass

        with open(control_file, 'w', encoding='utf-8') as f:
            json.dump({'interval': final_interval, 'timestamp': time.time()}, f)

        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(control_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if 'success' in result:
                    try:
                        os.remove(control_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        try:
            os.remove(control_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid interval value'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/toggle_auto_fill_authors', methods=['POST'])
def api_toggle_auto_fill_authors():
    data = request.json
    enabled = data.get('enabled', False)

    if IS_STANDALONE:
        standalone_manager.save_config({'auto_fill_authors': enabled})
        return jsonify({'success': True})

    try:
        control_file = os.path.join(PROJECT_DIR, 'gui_toggle_auto_fill_authors.json')

        # Clear existing
        if os.path.exists(control_file):
            try:
                os.remove(control_file)
            except Exception:
                pass

        # Write request
        with open(control_file, 'w', encoding='utf-8') as f:
            json.dump({'enabled': bool(enabled), 'timestamp': time.time()}, f)

        # Wait for bot response
        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(control_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if 'success' in result:
                    try:
                        os.remove(control_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        try:
            os.remove(control_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add_topic', methods=['POST'])
def api_add_topic():
    data = request.json
    topic = data.get('topic', '').strip()
    if not topic: return jsonify({'success': False})

    if IS_STANDALONE:
        cfg = standalone_manager.get_config()
        topics = cfg.get('additional_topics', {})
        cid = standalone_manager.channel_id
        lst = topics.get(cid, [])
        if topic not in lst and len(lst) < 6:
            lst.append(topic)
            topics[cid] = lst
            standalone_manager.save_config({'additional_topics': topics})
        return jsonify({'success': True})

    if not topic:
        return jsonify({'success': False, 'error': 'Topic text is required'})

    try:
        topic_file = os.path.join(PROJECT_DIR, 'gui_add_topic.json')

        # Clear any existing file first
        if os.path.exists(topic_file):
            try:
                os.remove(topic_file)
            except Exception:
                pass

        # Write request
        with open(topic_file, 'w', encoding='utf-8') as f:
            json.dump({'topic': topic, 'timestamp': time.time()}, f)

        # Wait for bot to process
        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(topic_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if 'success' in result:
                    try:
                        os.remove(topic_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        try:
            os.remove(topic_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove_topic', methods=['POST'])
def api_remove_topic():
    data = request.json
    topic = data.get('topic', '').strip()

    if IS_STANDALONE and topic:
        cfg = standalone_manager.get_config()
        topics = cfg.get('additional_topics', {})
        cid = standalone_manager.channel_id
        if cid in topics and topic in topics[cid]:
            topics[cid].remove(topic)
            standalone_manager.save_config({'additional_topics': topics})
        return jsonify({'success': True})

    if not topic:
        return jsonify({'success': False, 'error': 'Topic text is required'})

    try:
        topic_file = os.path.join(PROJECT_DIR, 'gui_remove_topic.json')

        if os.path.exists(topic_file):
            try:
                os.remove(topic_file)
            except Exception:
                pass

        with open(topic_file, 'w', encoding='utf-8') as f:
            json.dump({'topic': topic, 'timestamp': time.time()}, f)

        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(topic_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if 'success' in result:
                    try:
                        os.remove(topic_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        try:
            os.remove(topic_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear_topics', methods=['POST'])
def api_clear_topics():
    if IS_STANDALONE:
        cfg = standalone_manager.get_config()
        topics = cfg.get('additional_topics', {})
        cid = standalone_manager.channel_id
        if cid in topics:
            topics[cid] = []
            standalone_manager.save_config({'additional_topics': topics})
        return jsonify({'success': True})

    try:
        clear_file = os.path.join(PROJECT_DIR, 'gui_clear_topics.json')

        if os.path.exists(clear_file):
            try:
                os.remove(clear_file)
            except Exception:
                pass

        with open(clear_file, 'w', encoding='utf-8') as f:
            json.dump({'clear': True, 'timestamp': time.time()}, f)

        max_wait = 3
        waited = 0
        while waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
            try:
                with open(clear_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                if 'success' in result:
                    try:
                        os.remove(clear_file)
                    except Exception:
                        pass
                    return jsonify(result)
            except (json.JSONDecodeError, FileNotFoundError, KeyError):
                continue

        try:
            os.remove(clear_file)
        except Exception:
            pass

        return jsonify({'success': False, 'error': 'Timeout waiting for bot response'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/match_citations', methods=['POST'])
def api_match_citations():
    text = request.form.get('text', '')
    file = request.files.get('file')

    if not text:
        return jsonify({'success': False, 'error': 'No text provided'})
    if not file:
        return jsonify({'success': False, 'error': 'No file uploaded'})

    try:
        filename = secure_filename(file.filename)
        file_content = ""

        if filename.lower().endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                file_content += page.extract_text() + "\\n"
        elif filename.lower().endswith('.docx'):
            doc = docx.Document(file)
            for para in doc.paragraphs:
                file_content += para.text + "\n"
        elif filename.lower().endswith('.doc'):
            # Use macOS textutil for legacy .doc files
            try:
                process = subprocess.Popen(
                    ['textutil', '-convert', 'txt', '-format', 'doc', '-stdin', '-stdout'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate(input=file.read())
                if process.returncode == 0:
                    file_content = stdout.decode('utf-8', errors='ignore')
                else:
                    return jsonify({'success': False, 'error': f'Failed to process .doc file: {stderr.decode()}'})
            except Exception as e:
                return jsonify({'success': False, 'error': f'Error processing .doc file: {str(e)}'})
        elif filename.lower().endswith(('.xlsx', '.xls')):
            # Read all sheets, convert all cells to string
            xls = pd.ExcelFile(file)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                # Convert everything to string and join
                file_content += df.to_string() + "\\n"
        elif filename.lower().endswith('.txt'):
             file_content = file.read().decode('utf-8', errors='ignore')
        else:
            return jsonify({'success': False, 'error': 'Unsupported file format'})

        # Cross reference logic
        matches = []

        # Preprocessing regex for stripping prefixes (numbers, bullets, dots)
        prefix_pattern = re.compile(r'^[\d\.\s\-\*•]+')

        def normalize_text(text):
            """Normalize text for comparison: lowercase, remove punctuation, strip whitespace"""
            if not text:
                return ""
            # Lowercase
            text = text.lower()
            # Remove punctuation
            text = text.translate(str.maketrans('', '', string.punctuation))
            # Collapse whitespace
            text = ' '.join(text.split())
            return text

        def strip_prefix(text):
            """Remove list markers like '1.', '•', etc."""
            return prefix_pattern.sub('', text).strip()

        # Split content into lines and filter empty ones
        file_lines = [line for line in file_content.split('\n') if line.strip()]

        # Pre-process file lines for efficiency
        processed_file_lines = []
        for line in file_lines:
            stripped = strip_prefix(line)
            normalized = normalize_text(stripped)
            processed_file_lines.append({
                'original': line,
                'stripped': stripped,
                'normalized': normalized
            })

        # Normalize search text
        # Split input text into individual queries (newline separated)
        queries = [q.strip() for q in text.split('\n') if q.strip()]

        for query in queries:
            norm_query = normalize_text(query)
            if not norm_query:
                continue

            best_score = 0
            best_match = None

            for p_line in processed_file_lines:
                if not p_line['normalized']:
                    continue

                # Use partial_ratio because the search text (title) is likely a substring of the full citation
                score = fuzz.partial_ratio(norm_query, p_line['normalized'])

                if score > best_score:
                    best_score = score
                    best_match = p_line['stripped']

            # Threshold for match (85 is usually a good starting point for high confidence)
            if best_score >= 85 and best_match:
                matches.append(best_match)

        return jsonify({'success': True, 'matches': matches})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--standalone', '-s', action='store_true', help='Run in standalone mode (no Discord bot)')
    parser.add_argument('--port', type=int, default=8765, help='Web server port')
    args, unknown = parser.parse_known_args()

    global IS_STANDALONE, standalone_manager
    if args.standalone or os.getenv('ESP_STANDALONE') == '1':
        IS_STANDALONE = True
        standalone_manager = StandaloneManager()
        print("🔥 RUNNING IN STANDALONE MODE (No Discord Bot required)")

    port = args.port

    # Clear all stale GUI control files on startup for a fresh state
    stale_files = [
        COMPLETION_STATUS_FILE,
        CONTROL_FILL,
        ADD_CITATION_FILE,
        os.path.join(PROJECT_DIR, 'gui_queue.json'),
        os.path.join(PROJECT_DIR, 'gui_queue_request.json'),
        os.path.join(PROJECT_DIR, 'gui_clear_queue.json'),
        os.path.join(PROJECT_DIR, 'gui_pause.json'),
        os.path.join(PROJECT_DIR, 'gui_resume.json'),
        os.path.join(PROJECT_DIR, 'gui_skip.json'),
        os.path.join(PROJECT_DIR, 'gui_set_asset_type.json'),
        os.path.join(PROJECT_DIR, 'gui_set_researcher.json'),
        os.path.join(PROJECT_DIR, 'gui_add_topic.json'),
        os.path.join(PROJECT_DIR, 'gui_remove_topic.json'),
        os.path.join(PROJECT_DIR, 'gui_clear_topics.json'),
        os.path.join(PROJECT_DIR, 'gui_toggle_auto_fill_authors.json'),
        os.path.join(PROJECT_DIR, 'gui_set_author_add_delay.json'),
        os.path.join(PROJECT_DIR, 'gui_set_restart_policy.json'),
    ]

    cleared_count = 0
    for stale_file in stale_files:
        if os.path.exists(stale_file):
            try:
                os.remove(stale_file)
                cleared_count += 1
            except Exception as e:
                print(f"⚠️  Could not clear {os.path.basename(stale_file)}: {e}")

    if cleared_count > 0:
        print(f"🧹 Cleared {cleared_count} stale control file(s)")

    # Show configuration info
    print(f"📁 Bot config file: {BOT_CONFIG_FILE}")
    print(f"📺 Channel ID: {CITATION_CHANNEL_ID or 'Not set'}")

    # Check if port is already in use and try to kill the process
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()

    if result == 0:
        # Port is in use, try to kill the process
        print(f"⚠️  Port {port} is already in use. Attempting to free it...")
        try:
            # Try to find and kill the process using the port
            import subprocess
            # On macOS/Linux, find process using the port
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        subprocess.run(['kill', '-9', pid], timeout=1, capture_output=True)
                        print(f"✅ Killed process {pid} using port {port}")
                    except Exception:
                        pass
                time.sleep(0.5)  # Wait a bit for port to be released
        except Exception as e:
            print(f"⚠️  Could not free port {port}: {e}")
            print(f"💡 Please manually close the process using port {port} or restart your computer")
            return

    url = f'http://localhost:{port}'
    print(f"🌐 ESP GUI Server starting on {url}")
    print("📱 Opening browser...")
    print("💡 Press Ctrl+C or use 'Close Bot' button to exit")

    # Open browser after a short delay (skip in container/CI contexts)
    disable_browser_open = (os.getenv("NO_OPEN_BROWSER") or "").strip().lower() in {"1", "true", "yes"}
    if not disable_browser_open:
        def open_browser():
            time.sleep(1)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    # Run Flask app (env-configurable for container live-edit mode)
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    debug_mode = (os.getenv("FLASK_DEBUG") or "").strip().lower() in {"1", "true", "yes"}
    use_reloader = (os.getenv("FLASK_RELOAD") or "").strip().lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug_mode, use_reloader=use_reloader)

if __name__ == "__main__":
    main()
