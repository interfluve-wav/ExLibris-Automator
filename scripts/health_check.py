#!/usr/bin/env python3
"""
Health check script for Esploro Citation Bot.

Returns:
    0 - All checks passed
    1 - Warning (non-critical issues)
    2 - Critical failure
"""
import os
import sys
import json
import psutil
from pathlib import Path
from datetime import datetime, timedelta


def check_config_files():
    """Check if config files exist and are valid JSON."""
    files = ['bot_config.json', 'citations_config.json']
    for filename in files:
        if not Path(filename).exists():
            print(f"❌ {filename} not found")
            return False
        try:
            with open(filename) as f:
                json.load(f)
        except json.JSONDecodeError:
            print(f"❌ {filename} is not valid JSON")
            return False
    print("✓ Config files OK")
    return True


def check_disk_space():
    """Check if sufficient disk space is available."""
    usage = psutil.disk_usage('.')
    free_gb = usage.free / (1024 ** 3)
    if free_gb < 2:
        print(f"❌ Low disk space: {free_gb:.1f} GB free")
        return False
    elif free_gb < 5:
        print(f"⚠️  Warning: {free_gb:.1f} GB free (recommended: 5+ GB)")
        return True
    print(f"✓ Disk space OK: {free_gb:.1f} GB free")
    return True


def check_logs():
    """Check if log directory exists and has recent activity."""
    log_dir = Path('logs')
    if not log_dir.exists():
        print("⚠️  Logs directory does not exist (will be created)")
        return True

    # Check for recent log files (within last 24 hours)
    recent_logs = []
    cutoff = datetime.now() - timedelta(days=1)
    for log_file in log_dir.glob('*.log'):
        if datetime.fromtimestamp(log_file.stat().st_mtime) > cutoff:
            recent_logs.append(log_file)

    if recent_logs:
        print(f"✓ Logs OK: {len(recent_logs)} recent log files")
    else:
        print("⚠️  No recent log files (bot may not be running)")
    return True


def check_worker_process():
    """Check if worker process is running."""
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'automation.worker' in cmdline or 'automation/worker.py' in cmdline:
                print(f"✓ Worker process running (PID: {proc.pid})")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    print("⚠️  No worker process found (starts when needed)")
    return True


def check_bot_process():
    """Check if Discord bot process is running."""
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'discord_bot_batch_smart.py' in cmdline:
                cpu_percent = proc.cpu_percent(interval=0.1)
                mem_mb = proc.memory_info().rss / (1024 ** 2)
                print(f"✓ Bot process running (PID: {proc.pid}, CPU: {cpu_percent:.1f}%, MEM: {mem_mb:.1f} MB)")

                # Check resource usage
                if cpu_percent > 80:
                    print(f"⚠️  High CPU usage: {cpu_percent:.1f}%")
                if mem_mb > 1500:
                    print(f"⚠️  High memory usage: {mem_mb:.1f} MB")

                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    print("❌ Discord bot is not running")
    return False


def check_control_files():
    """Check control files for stuck states."""
    control_files = list(Path('.').glob('citation_control_*.json'))
    status_files = list(Path('.').glob('citation_status_*.json'))

    if control_files or status_files:
        print(f"ℹ️  Active sessions: {len(control_files)} control, {len(status_files)} status files")

        # Check for old control files (> 1 hour)
        cutoff = datetime.now() - timedelta(hours=1)
        for f in control_files:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                print(f"⚠️  Stale control file: {f.name} (> 1 hour old)")

    return True


def main():
    """Run all health checks."""
    print("🏥 Esploro Bot Health Check")
    print("=" * 50)

    checks = [
        ("Config Files", check_config_files),
        ("Disk Space", check_disk_space),
        ("Logs", check_logs),
        ("Bot Process", check_bot_process),
        ("Worker Process", check_worker_process),
        ("Control Files", check_control_files),
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"❌ {name}: Error - {e}")
            results[name] = False
        print()

    # Evaluate results
    critical_checks = ["Config Files", "Bot Process"]
    critical_failed = any(not results.get(check, True) for check in critical_checks)

    if critical_failed:
        print("💀 CRITICAL: Bot is not healthy")
        return 2
    elif not all(results.values()):
        print("⚠️  WARNING: Some checks failed")
        return 1
    else:
        print("✅ ALL CHECKS PASSED: Bot is healthy")
        return 0


if __name__ == '__main__':
    sys.exit(main())
