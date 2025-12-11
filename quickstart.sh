#!/bin/bash
# RepairShopr-Onyx Bridge Quick Start
#
# This script helps you get started quickly.
# Run: ./quickstart.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     ${BOLD}RepairShopr → Onyx Bridge${NC}${BLUE}                                 ║"
echo "║     Quick Start Setup                                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if credentials are already set
if [ -n "$RS_SUBDOMAIN" ] && [ -n "$RS_API_KEY" ]; then
    echo -e "${GREEN}✓ Credentials found in environment${NC}"
    echo "  Subdomain: $RS_SUBDOMAIN"
    echo ""
else
    echo -e "${BOLD}Step 1: Enter your RepairShopr credentials${NC}"
    echo ""

    # Get subdomain
    echo "Your RepairShopr subdomain (the part before .repairshopr.com)"
    echo -e "Example: If your URL is https://${BLUE}acmerepair${NC}.repairshopr.com, enter: acmerepair"
    read -p "Subdomain: " RS_SUBDOMAIN

    if [ -z "$RS_SUBDOMAIN" ]; then
        echo -e "${RED}✗ Subdomain is required${NC}"
        exit 1
    fi

    echo ""
    echo "Your API key (from RepairShopr → Profile → API Tokens)"
    read -sp "API Key: " RS_API_KEY
    echo ""

    if [ -z "$RS_API_KEY" ]; then
        echo -e "${RED}✗ API key is required${NC}"
        exit 1
    fi

    export RS_SUBDOMAIN
    export RS_API_KEY
fi

# Check Python
echo ""
echo -e "${BOLD}Step 2: Checking Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "${RED}✗ Python not found. Please install Python 3.11+${NC}"
    exit 1
fi

PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✓ Found Python $PY_VERSION${NC}"

# Install if needed
echo ""
echo -e "${BOLD}Step 3: Installing connector...${NC}"
if ! $PYTHON -c "import repairshopr_connector" &> /dev/null; then
    echo "Installing from source..."
    $PYTHON -m pip install -e . --quiet
    echo -e "${GREEN}✓ Installed${NC}"
else
    echo -e "${GREEN}✓ Already installed${NC}"
fi

# Test connection
echo ""
echo -e "${BOLD}Step 4: Testing connection to RepairShopr...${NC}"
if $PYTHON -m repairshopr_connector.cli test; then
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}Setup Complete!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Next steps:"
    echo ""
    echo "  1. Run a sync to fetch your data:"
    echo -e "     ${BLUE}rs-onyx sync${NC}"
    echo ""
    echo "  2. To make credentials persistent, add to your shell profile:"
    echo -e "     ${BLUE}export RS_SUBDOMAIN=$RS_SUBDOMAIN${NC}"
    echo -e "     ${BLUE}export RS_API_KEY=your-api-key${NC}"
    echo ""
    echo "  3. Or run interactive setup to save to config file:"
    echo -e "     ${BLUE}rs-onyx setup${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}Connection failed. Please check your credentials.${NC}"
    exit 1
fi
