# Production Deployment Guide

This guide covers various deployment methods for the Esploro Citation Automation bot in production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Docker Deployment](#docker-deployment)
3. [Linux Server Deployment (systemd)](#linux-server-deployment-systemd)
4. [Environment Variables](#environment-variables)
5. [Security Best Practices](#security-best-practices)
6. [Monitoring and Logging](#monitoring-and-logging)
7. [Backup and Recovery](#backup-and-recovery)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required
- Python 3.10 or higher
- Docker and Docker Compose (for Docker deployment)
- Linux server with systemd (for service deployment)
- Valid OpenAI API key
- Discord bot token with proper permissions
- Esploro account credentials

### Recommended
- 2GB+ RAM
- 2+ CPU cores
- 10GB+ disk space for logs and data
- SSL certificate for production domains (if using web interface)

---

## Docker Deployment

### Quick Start with Docker Compose

1. **Clone the repository**:
   ```bash
   git clone https://github.com/interfluve-wav/esp---warp.git
   cd esp---warp
   ```

2. **Create environment file**:
   ```bash
   cp docs/ENV_EXAMPLE.md .env
   # Edit .env with your credentials
   nano .env
   ```

3. **Required environment variables**:
   ```bash
   OPENAI_API_KEY=sk-proj-...
   ESPLORO_USERNAME=your.username
   ESPLORO_PASSWORD=your_password
   DISCORD_BOT_TOKEN=your_discord_token
   CITATION_CHANNEL_ID=123456789  # Optional: restrict to one channel
   DISCORD_GUILD_ID=987654321     # Optional: for faster slash command sync
   HEADLESS=1                      # Required for Docker
   ```

4. **Build and start**:
   ```bash
   docker-compose up -d
   ```

5. **View logs**:
   ```bash
   docker-compose logs -f esp-bot
   ```

6. **Stop the bot**:
   ```bash
   docker-compose down
   ```

### Docker Commands

```bash
# Rebuild after code changes
docker-compose up -d --build

# Restart the bot
docker-compose restart esp-bot

# Check status
docker-compose ps

# Access container shell
docker-compose exec esp-bot /bin/bash

# View resource usage
docker stats esp-bot
```

### Production Docker Configuration

For production, edit `docker-compose.yml` to:

1. **Enable auto-restart**:
   ```yaml
   restart: unless-stopped
   ```

2. **Set resource limits**:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2.0'
         memory: 2G
   ```

3. **Mount persistent volumes**:
   ```yaml
   volumes:
     - ./logs:/app/logs
     - ./data:/app/data
     - ./bot_config.json:/app/bot_config.json
   ```

4. **Add monitoring** (optional):
   - Uncomment Prometheus/Grafana sections in docker-compose.yml
   - Access Grafana at http://localhost:3000

---

## Linux Server Deployment (systemd)

### Installation

1. **Create dedicated user**:
   ```bash
   sudo useradd -r -m -s /bin/bash espbot
   sudo usermod -aG sudo espbot  # Optional: for updates
   ```

2. **Install to /opt**:
   ```bash
   sudo mkdir -p /opt/esploro-bot
   sudo chown espbot:espbot /opt/esploro-bot
   sudo -u espbot git clone https://github.com/interfluve-wav/esp---warp.git /opt/esploro-bot
   ```

3. **Set up Python environment**:
   ```bash
   cd /opt/esploro-bot
   sudo -u espbot python3 -m venv .venv
   sudo -u espbot .venv/bin/pip install -r requirements.txt
   sudo -u espbot .venv/bin/python -m playwright install chromium
   ```

4. **Configure environment**:
   ```bash
   sudo -u espbot cp docs/ENV_EXAMPLE.md .env
   sudo -u espbot nano .env
   # Set all required variables
   ```

5. **Create data directories**:
   ```bash
   sudo -u espbot mkdir -p /opt/esploro-bot/logs /opt/esploro-bot/data
   sudo chmod 750 /opt/esploro-bot/logs /opt/esploro-bot/data
   ```

6. **Install systemd service**:
   ```bash
   sudo cp deployment/esploro-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable esploro-bot
   sudo systemctl start esploro-bot
   ```

### Service Management

```bash
# Start the service
sudo systemctl start esploro-bot

# Stop the service
sudo systemctl stop esploro-bot

# Restart the service
sudo systemctl restart esploro-bot

# Check status
sudo systemctl status esploro-bot

# View logs (real-time)
sudo journalctl -u esploro-bot -f

# View logs (last 100 lines)
sudo journalctl -u esploro-bot -n 100

# View logs (since boot)
sudo journalctl -u esploro-bot -b
```

### Updating the Application

```bash
# Stop the service
sudo systemctl stop esploro-bot

# Pull updates
cd /opt/esploro-bot
sudo -u espbot git pull

# Update dependencies (if requirements.txt changed)
sudo -u espbot .venv/bin/pip install -r requirements.txt

# Restart the service
sudo systemctl start esploro-bot

# Verify it's running
sudo systemctl status esploro-bot
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `ESPLORO_USERNAME` | Esploro login username | `john.doe` |
| `ESPLORO_PASSWORD` | Esploro login password | `SecurePass123!` |
| `DISCORD_BOT_TOKEN` | Discord bot token | `MTIzNDU2Nzg5...` |

### Recommended Variables

| Variable | Description | Default | Production Value |
|----------|-------------|---------|------------------|
| `HEADLESS` | Run browser headless | `0` | `1` |
| `LOG_LEVEL` | Logging verbosity | `INFO` | `INFO` or `WARN` |
| `CITATION_PARSER` | Parser to use | `openai` | `openai` |
| `OPENAI_MODEL` | OpenAI model | `gpt-4o-mini` | `gpt-4o-mini` |

### Optional Variables

| Variable | Description | When to Use |
|----------|-------------|-------------|
| `CITATION_CHANNEL_ID` | Restrict to one channel | Single-channel deployment |
| `DISCORD_GUILD_ID` | Server ID for fast slash sync | Always recommended |
| `DEFAULT_RESEARCHER` | Default researcher name | To pre-fill forms |

### Validating Environment

Run the validation script before deployment:

```bash
./start_smart_batch.sh --check
```

This will verify:
- All required variables are set
- Python version is 3.10+
- All dependencies are installed
- Playwright browsers are available

---

## Security Best Practices

### 1. Credentials Management

**DO NOT** store credentials in code or commit .env to git:

```bash
# Ensure .env is in .gitignore
echo ".env" >> .gitignore

# Set proper permissions
chmod 600 .env
```

**Recommended**: Use a secrets manager:
- AWS Secrets Manager
- HashiCorp Vault
- Azure Key Vault
- Docker Secrets (for Docker Swarm)

### 2. Network Security

**Docker**:
```yaml
# Use internal networks
networks:
  esp-network:
    internal: true  # No external access
```

**Firewall** (UFW example):
```bash
# Allow only SSH
sudo ufw allow ssh
sudo ufw enable

# Block all other incoming by default
sudo ufw default deny incoming
sudo ufw default allow outgoing
```

### 3. Resource Limits

Set limits to prevent DoS:

**Docker**:
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
```

**systemd**:
```ini
MemoryLimit=2G
CPUQuota=200%
LimitNOFILE=4096
```

### 4. Regular Updates

```bash
# Update dependencies monthly
pip install --upgrade -r requirements.txt

# Check for security vulnerabilities
pip-audit -r requirements.txt
safety check --file requirements.txt
```

### 5. Input Validation

The bot now includes input validation (v1.1.0+):
- Citation length limits (20-5000 characters)
- Researcher name validation
- XSS/injection protection

---

## Monitoring and Logging

### Log Locations

**Docker**:
- Container logs: `docker-compose logs esp-bot`
- Mounted logs: `./logs/` directory

**systemd**:
- System logs: `journalctl -u esploro-bot`
- Application logs: `/opt/esploro-bot/logs/`

### Log Levels

Configure via `LOG_LEVEL` environment variable:
- `DEBUG`: All messages (verbose)
- `INFO`: Normal operations
- `WARN`: Warnings and errors
- `ERROR`: Errors only

### Monitoring Metrics

**Key metrics to monitor**:
1. Citation processing rate (citations/hour)
2. OpenAI API errors and timeouts
3. Worker process crashes
4. Memory usage
5. Disk space (logs and data directories)

**Prometheus/Grafana** (optional):
1. Uncomment monitoring sections in docker-compose.yml
2. Access Grafana: http://localhost:3000
3. Default credentials: admin/admin
4. Import dashboard from monitoring/grafana-dashboard.json

### Alerting

Set up alerts for:
- High error rates (> 10% of requests)
- Worker process down for > 5 minutes
- Disk usage > 80%
- Memory usage > 90%

**Example with journalctl**:
```bash
# Alert on errors
journalctl -u esploro-bot -f | grep -i "error" | \
  while read line; do
    echo "ERROR DETECTED: $line" | mail -s "Esploro Bot Error" admin@example.com
  done
```

---

## Backup and Recovery

### Files to Back Up

1. **Configuration**:
   - `.env` (credentials)
   - `bot_config.json` (bot state)
   - `citations_config.json` (citation rules)

2. **Data**:
   - `logs/` directory
   - `data/` directory (CSV outputs)
   - `citationsPresentations.csv`

### Backup Script

```bash
#!/bin/bash
# backup.sh - Back up Esploro bot data

BACKUP_DIR="/backup/esploro-bot"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.tar.gz"

mkdir -p "$BACKUP_DIR"

cd /opt/esploro-bot
tar -czf "$BACKUP_FILE" \
  .env \
  bot_config.json \
  citations_config.json \
  logs/ \
  data/ \
  citationsPresentations.csv

echo "Backup created: $BACKUP_FILE"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +7 -delete
```

**Automate backups** with cron:
```bash
# Add to crontab
0 2 * * * /opt/esploro-bot/scripts/backup.sh
```

### Recovery Procedure

1. **Stop the service**:
   ```bash
   sudo systemctl stop esploro-bot
   ```

2. **Extract backup**:
   ```bash
   cd /opt/esploro-bot
   tar -xzf /backup/esploro-bot/backup_YYYYMMDD_HHMMSS.tar.gz
   ```

3. **Verify permissions**:
   ```bash
   sudo chown -R espbot:espbot /opt/esploro-bot
   ```

4. **Restart service**:
   ```bash
   sudo systemctl start esploro-bot
   sudo systemctl status esploro-bot
   ```

---

## Troubleshooting

### Bot Not Starting

**Check logs**:
```bash
# Docker
docker-compose logs esp-bot

# systemd
sudo journalctl -u esploro-bot -n 50
```

**Common issues**:
1. Missing environment variables
   - Solution: Run `./start_smart_batch.sh --check`
2. Playwright not installed
   - Solution: `python -m playwright install chromium`
3. Permission errors
   - Solution: `sudo chown -R espbot:espbot /opt/esploro-bot`

### OpenAI Timeout Errors

**Symptoms**: `OpenAI API error: timeout`

**Solutions**:
1. Check network connectivity
2. Verify API key is valid
3. Check OpenAI status: https://status.openai.com/
4. Increase timeout (edit openai_parser.py line 167)

### Worker Process Crashes

**Check control files**:
```bash
ls -la citation_control_*.json citation_status_*.json
cat citation_status_<channel_id>.json
```

**Common causes**:
1. Browser crash → Restart worker with `!close` then `!f`
2. Memory exhaustion → Increase resource limits
3. Playwright error → Reinstall: `python -m playwright install chromium`

### High Memory Usage

**Check usage**:
```bash
# Docker
docker stats esp-bot

# System
top -p $(pgrep -f discord_bot_batch_smart.py)
```

**Solutions**:
1. Clear old logs: `find logs/ -mtime +30 -delete`
2. Restart bot regularly (e.g., daily cron)
3. Increase memory limits in docker-compose.yml or systemd service

### Slash Commands Not Appearing

**Solutions**:
1. Set `DISCORD_GUILD_ID` in .env
2. Run `!resync` in Discord
3. Wait up to 1 minute for sync
4. Verify bot has `applications.commands` scope

---

## Performance Tuning

### OpenAI Rate Limits

**Current limits** (as of 2024):
- gpt-4o-mini: 500 requests/min, 200k tokens/min
- gpt-4o: 10k requests/day (varies by tier)

**Recommendations**:
1. Use gpt-4o-mini for cost efficiency
2. Monitor usage: https://platform.openai.com/usage
3. Implement request queuing for high-volume use

### Caching

The bot includes response caching (100-item LRU cache):
- Cache hit = near-instant processing
- Cache miss = 1-3 seconds (API call)
- Cache is in-memory only (resets on restart)

**To increase cache size**, edit `openai_parser.py`:
```python
_response_cache = OrderedDict()  # Line 61
_cache_max_size = 200  # Increase from 100
```

---

## Support and Maintenance

### Regular Maintenance Tasks

**Weekly**:
- Check logs for errors
- Verify disk space
- Review citation processing stats

**Monthly**:
- Update dependencies: `pip install --upgrade -r requirements.txt`
- Run security audit: `pip-audit`
- Back up configuration files

**Quarterly**:
- Review and rotate API keys
- Update Playwright: `python -m playwright install chromium`
- Test disaster recovery procedure

### Getting Help

- GitHub Issues: https://github.com/interfluve-wav/esp---warp/issues
- Documentation: See docs/INDEX.md
- Logs: Always include logs when reporting issues

---

## Production Checklist

Before going to production:

- [ ] All environment variables configured and validated
- [ ] Bot tested in non-production Discord server
- [ ] Backups configured and tested
- [ ] Monitoring and alerting set up
- [ ] Resource limits configured appropriately
- [ ] Security hardening applied (firewall, permissions)
- [ ] Disaster recovery procedure documented and tested
- [ ] Team trained on bot operation and troubleshooting
- [ ] Documentation reviewed and updated
- [ ] Performance benchmarks recorded

---

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [systemd Service Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [Discord Bot Best Practices](https://discord.com/developers/docs/topics/best-practices)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Playwright Documentation](https://playwright.dev/python/)

---

**Last Updated**: February 2026
**Version**: 1.1.0
