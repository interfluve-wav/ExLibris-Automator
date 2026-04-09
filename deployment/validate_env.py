#!/usr/bin/env python3
"""
Environment validation script for Esploro Citation Automation.

Validates all environment variables, dependencies, and system requirements
before deployment.
"""
import os
import sys
import subprocess
from pathlib import Path


class Colors:
    """Terminal colors for output."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.RESET}\n")


def print_success(text):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_warning(text):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def check_python_version():
    """Check if Python version meets requirements."""
    print_header("Python Version Check")
    
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}"
    
    if major >= 3 and minor >= 10:
        print_success(f"Python {version_str} (meets requirement: 3.10+)")
        return True
    else:
        print_error(f"Python {version_str} (requires 3.10+)")
        return False


def check_environment_variables():
    """Check required environment variables."""
    print_header("Environment Variables Check")
    
    required = {
        'OPENAI_API_KEY': 'OpenAI API key',
        'ESPLORO_USERNAME': 'Esploro username',
        'ESPLORO_PASSWORD': 'Esploro password',
        'DISCORD_BOT_TOKEN': 'Discord bot token',
    }
    
    recommended = {
        'CITATION_PARSER': 'Citation parser (should be "openai")',
        'OPENAI_MODEL': 'OpenAI model (default: gpt-4o-mini)',
        'HEADLESS': 'Browser headless mode (1 for production)',
        'LOG_LEVEL': 'Logging level (INFO recommended)',
    }
    
    optional = {
        'CITATION_CHANNEL_ID': 'Restrict to single channel',
        'DISCORD_GUILD_ID': 'For fast slash command sync',
        'DEFAULT_RESEARCHER': 'Default researcher name',
    }
    
    all_valid = True
    
    # Check required
    print(f"{Colors.BOLD}Required Variables:{Colors.RESET}")
    for var, description in required.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            display_value = f"{value[:8]}..." if len(value) > 8 else "***"
            print_success(f"{var}: {display_value} ({description})")
        else:
            print_error(f"{var}: NOT SET ({description})")
            all_valid = False
    
    # Check recommended
    print(f"\n{Colors.BOLD}Recommended Variables:{Colors.RESET}")
    for var, description in recommended.items():
        value = os.getenv(var)
        if value:
            print_success(f"{var}: {value} ({description})")
        else:
            print_warning(f"{var}: not set ({description})")
    
    # Check optional
    print(f"\n{Colors.BOLD}Optional Variables:{Colors.RESET}")
    for var, description in optional.items():
        value = os.getenv(var)
        if value:
            print_success(f"{var}: {value} ({description})")
        else:
            print(f"  {var}: not set ({description})")
    
    return all_valid


def check_dependencies():
    """Check if required Python packages are installed."""
    print_header("Python Dependencies Check")
    
    required_packages = [
        'playwright',
        'dotenv',
        'requests',
        'flask',
        'openai',
        'discord',
    ]
    
    all_installed = True
    
    for package in required_packages:
        try:
            __import__(package)
            # Get version if possible
            try:
                mod = __import__(package)
                version = getattr(mod, '__version__', 'unknown')
                print_success(f"{package}: installed (version {version})")
            except:
                print_success(f"{package}: installed")
        except ImportError:
            print_error(f"{package}: NOT INSTALLED")
            all_installed = False
    
    if not all_installed:
        print_warning("\nInstall missing packages with: pip install -r requirements.txt")
    
    return all_installed


def check_playwright():
    """Check if Playwright is installed and browsers are available."""
    print_header("Playwright Browser Check")
    python_executable = sys.executable or 'python3'
    
    try:
        result = subprocess.run(
            [python_executable, '-m', 'playwright', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_success(f"Playwright: {version}")
        else:
            print_error("Playwright: installed but version check failed")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print_error("Playwright: NOT INSTALLED")
        print_warning("Install with: python -m playwright install chromium")
        return False
    
    # Check if chromium is installed
    try:
        result = subprocess.run(
            [python_executable, '-c', 'from playwright.sync_api import sync_playwright; sync_playwright().start()'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print_success("Chromium browser: available")
            return True
        else:
            print_warning("Chromium browser: may need installation")
            print_warning("Install with: python -m playwright install chromium")
            return True  # Playwright is installed, just needs browsers
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print_warning("Could not verify Chromium installation")
        return True


def check_files():
    """Check if required configuration files exist."""
    print_header("Configuration Files Check")
    
    required_files = [
        'bot_config.json',
        'citations_config.json',
    ]
    
    optional_files = [
        '.env',
        'requirements.txt',
        'discord_bot_batch_smart.py',
        'openai_parser.py',
    ]
    
    all_exist = True
    
    print(f"{Colors.BOLD}Required Files:{Colors.RESET}")
    for filename in required_files:
        if Path(filename).exists():
            print_success(f"{filename}: exists")
        else:
            print_error(f"{filename}: NOT FOUND")
            all_exist = False
    
    print(f"\n{Colors.BOLD}Core Files:{Colors.RESET}")
    for filename in optional_files:
        if Path(filename).exists():
            print_success(f"{filename}: exists")
        else:
            print_warning(f"{filename}: not found")
    
    return all_exist


def check_directories():
    """Check if required directories exist and are writable."""
    print_header("Directory Permissions Check")
    
    directories = [
        'logs',
        'automation',
        'utils',
    ]
    
    all_valid = True
    
    for dirname in directories:
        dirpath = Path(dirname)
        if dirpath.exists():
            if os.access(dirpath, os.W_OK):
                print_success(f"{dirname}/: exists and writable")
            else:
                print_warning(f"{dirname}/: exists but NOT writable")
                all_valid = False
        else:
            print_warning(f"{dirname}/: does not exist (will be created)")
    
    return all_valid


def check_disk_space():
    """Check available disk space."""
    print_header("Disk Space Check")
    
    try:
        stat = os.statvfs('.')
        available_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
        used_percent = ((total_gb - available_gb) / total_gb) * 100
        
        if available_gb > 10:
            print_success(f"Disk space: {available_gb:.1f} GB available ({used_percent:.1f}% used)")
            return True
        elif available_gb > 5:
            print_warning(f"Disk space: {available_gb:.1f} GB available ({used_percent:.1f}% used)")
            print_warning("Consider freeing up space for logs and data")
            return True
        else:
            print_error(f"Disk space: {available_gb:.1f} GB available ({used_percent:.1f}% used)")
            print_error("Insufficient disk space (need at least 5 GB)")
            return False
    except Exception as e:
        print_warning(f"Could not check disk space: {e}")
        return True


def main():
    """Run all validation checks."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║     Esploro Citation Automation - Environment Validation          ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(Colors.RESET)
    
    # Load .env if it exists
    if Path('.env').exists():
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print_success("Loaded environment variables from .env")
        except ImportError:
            print_warning("python-dotenv not installed, cannot load .env file")
    
    # Run all checks
    checks = [
        ("Python Version", check_python_version),
        ("Environment Variables", check_environment_variables),
        ("Python Dependencies", check_dependencies),
        ("Playwright", check_playwright),
        ("Configuration Files", check_files),
        ("Directories", check_directories),
        ("Disk Space", check_disk_space),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print_error(f"Check failed with exception: {e}")
            results[name] = False
    
    # Summary
    print_header("Validation Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        if result:
            print_success(f"{name}: PASSED")
        else:
            print_error(f"{name}: FAILED")
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} checks passed{Colors.RESET}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ All checks passed! Ready for deployment.{Colors.RESET}\n")
        return 0
    elif passed >= total - 2:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ Most checks passed. Review warnings before deployment.{Colors.RESET}\n")
        return 1
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ Multiple checks failed. Fix errors before deployment.{Colors.RESET}\n")
        return 2


if __name__ == '__main__':
    sys.exit(main())
