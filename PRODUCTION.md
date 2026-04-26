# Production Deployment & Automation Guide

## Quick Links

- **Deployment Guide**: [deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md) - Complete production deployment instructions
- **Environment Validation**: Run `python3 deployment/validate_env.py` before deployment
- **Health Check**: Run `python3 scripts/health_check.py` to check bot status
- **CI/CD Pipeline**: [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml)

## Deployment Options

### 1. Docker (Recommended for Production)

**Quick Start**:
```bash
# Copy and configure environment
cp docs/ENV_EXAMPLE.md .env
nano .env  # Set your credentials

# Start with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f esp-bot

# Stop
docker-compose down
```

**Features**:
- ✅ Isolated environment
- ✅ Automatic restarts
- ✅ Resource limits (2GB RAM, 2 CPU)
- ✅ Health checks built-in
- ✅ Non-root user for security

### 2. Linux Server (systemd)

**Installation**:
```bash
# Create service user
sudo useradd -r -m espbot

# Install to /opt
sudo mkdir -p /opt/esploro-bot
sudo chown espbot:espbot /opt/esploro-bot
sudo -u espbot git clone <repo-url> /opt/esploro-bot

# Setup Python environment
cd /opt/esploro-bot
sudo -u espbot python3 -m venv .venv
sudo -u espbot .venv/bin/pip install -r requirements.txt
sudo -u espbot .venv/bin/python -m playwright install chromium

# Configure environment
sudo -u espbot cp docs/ENV_EXAMPLE.md .env
sudo -u espbot nano .env

# Install and start service
sudo cp deployment/esploro-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable esploro-bot
sudo systemctl start esploro-bot
```

**Service Management**:
```bash
sudo systemctl status esploro-bot    # Check status
sudo systemctl restart esploro-bot   # Restart
sudo journalctl -u esploro-bot -f    # View logs
```

### 3. Development/Local

Use the existing `start_smart_batch.sh` script:
```bash
./start_smart_batch.sh
```

## Pre-Deployment Checklist

Run the validation script to ensure everything is configured correctly:

```bash
python3 deployment/validate_env.py
```

This checks:
- ✅ Python version (3.10+)
- ✅ All required environment variables
- ✅ Python dependencies installed
- ✅ Playwright browsers available
- ✅ Configuration files valid
- ✅ Sufficient disk space

## Monitoring & Maintenance

### Health Checks

Check bot health anytime:
```bash
python3 scripts/health_check.py
```

Returns:
- **0**: All checks passed
- **1**: Warnings (non-critical)
- **2**: Critical failure

### Automated Monitoring

**Docker**: Health checks run every 30 seconds automatically

**systemd**: Set up a cron job:
```bash
# Add to crontab
*/5 * * * * /opt/esploro-bot/.venv/bin/python3 /opt/esploro-bot/scripts/health_check.py
```

### Logs

**Docker**:
```bash
docker-compose logs -f esp-bot
# Or access mounted logs
cat ./logs/*.log
```

**systemd**:
```bash
sudo journalctl -u esploro-bot -f
# Or application logs
cat /opt/esploro-bot/logs/*.log
```

## Security Improvements (v1.1.0)

### Input Validation

All user inputs are now validated:
- Citation length limits (20-5000 characters)
- Researcher name format validation
- XSS/injection protection
- Sanitization of special characters

### API Security

- OpenAI API calls have 30-second timeout
- Better error handling with specific exception types
- Logging of validation failures

### Thread Safety

Fixed critical bug in ConfigManager where threading locks were not properly reused.

## CI/CD Pipeline

Automated GitHub Actions workflow runs on every push/PR:

1. **Linting & Testing**
   - Syntax checking with flake8
   - Code formatting with black
   - Unit and integration tests

2. **Security Scans**
   - Secrets scanning with TruffleHog
   - Dependency vulnerabilities with safety and pip-audit

3. **Docker Build**
   - Validates Dockerfile builds successfully
   - Uses GitHub Actions cache for faster builds

4. **Performance Benchmarks**
   - Runs performance tests on PRs
   - Posts results as PR comment

## Updating Dependencies

Run the update script:
```bash
./scripts/update_dependencies.sh
```

This will:
1. Check for outdated packages
2. Run security audits (pip-audit, safety)
3. Optionally update all packages
4. Generate new requirements.txt with pinned versions

## Performance Optimizations

The codebase has been optimized for production use:

- **Response Caching**: 100-item LRU cache for OpenAI API responses (>100x speedup on cache hits)
- **Config I/O**: In-memory config cache with debounced writes (>10x faster, 90% fewer disk writes)
- **Command Handling**: Consolidated dispatch table reduces code duplication by 60%
- **Parser Refactoring**: 40% reduction in complexity for title extraction logic

See [OPTIMIZATIONS_2026-02.md](OPTIMIZATIONS_2026-02.md) for details.

## Troubleshooting

### Bot Won't Start

1. Run validation: `python3 deployment/validate_env.py`
2. Check logs: `docker-compose logs` or `journalctl -u esploro-bot`
3. Verify environment variables are set correctly
4. Ensure Playwright is installed: `python -m playwright install chromium`

### High Memory Usage

1. Check with: `docker stats esp-bot` or `python3 scripts/health_check.py`
2. Clear old logs: `find logs/ -mtime +30 -delete`
3. Restart bot: `docker-compose restart` or `sudo systemctl restart esploro-bot`
4. Increase memory limits in docker-compose.yml or systemd service

### OpenAI API Errors

1. Verify API key: Check .env file
2. Check quota: Visit https://platform.openai.com/usage
3. Check status: https://status.openai.com/
4. Review logs for rate limiting messages

### Worker Process Crashes

1. Check browser automation logs in `logs/` directory
2. Verify Playwright is installed correctly
3. Try `!close` then `!f` in Discord to restart
4. Check for Esploro login issues

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check docs/INDEX.md for all documentation
- Review deployment/DEPLOYMENT.md for detailed guides

## Version History

- **v1.1.0** (2026-02): Security fixes, input validation, deployment infrastructure
- **v1.0.0** (2026-02): Performance optimizations, response caching, refactored parser
