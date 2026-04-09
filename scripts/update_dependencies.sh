#!/bin/bash
# update_dependencies.sh - Update and audit Python dependencies

set -e

echo "🔍 Checking for outdated packages..."
pip list --outdated

echo ""
echo "🔐 Running security audit with pip-audit..."
pip-audit -r requirements.txt || true

echo ""
echo "🛡️  Running security check with safety..."
safety check --file requirements.txt || true

echo ""
read -p "Do you want to update all packages to latest versions? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📦 Updating packages..."
    pip install --upgrade -r requirements.txt

    echo "💾 Generating new requirements.txt with pinned versions..."
    pip freeze > requirements.txt.new

    echo "✅ New requirements saved to requirements.txt.new"
    echo "Review and rename to requirements.txt if everything looks good"
else
    echo "Skipped update"
fi

echo ""
echo "✅ Dependency check complete!"
