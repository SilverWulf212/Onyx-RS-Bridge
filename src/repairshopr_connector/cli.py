#!/usr/bin/env python3
"""
RepairShopr-Onyx Bridge CLI

Easy setup and management tool for Lance and the team.

Usage:
    rs-onyx setup          # Interactive setup wizard
    rs-onyx test           # Test your connection
    rs-onyx sync           # Run a full sync
    rs-onyx status         # Show sync status
    rs-onyx stats          # Show statistics
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add color support
try:
    from colorama import Fore, Style, init
    init()
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    BLUE = Fore.CYAN
    RESET = Style.RESET_ALL
    BOLD = Style.BRIGHT
except ImportError:
    GREEN = RED = YELLOW = BLUE = RESET = BOLD = ""


def print_banner():
    """Print the banner."""
    print(f"""
{BLUE}╔══════════════════════════════════════════════════════════════╗
║     {BOLD}RepairShopr → Onyx Bridge{RESET}{BLUE}                                 ║
║     AI-Powered Knowledge Base for Your Repair Shop             ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def print_success(msg: str):
    print(f"{GREEN}✓ {msg}{RESET}")


def print_error(msg: str):
    print(f"{RED}✗ {msg}{RESET}")


def print_warning(msg: str):
    print(f"{YELLOW}⚠ {msg}{RESET}")


def print_info(msg: str):
    print(f"{BLUE}ℹ {msg}{RESET}")


def get_config_path() -> Path:
    """Get the configuration file path."""
    return Path.home() / ".onyx-rs-bridge" / "config.json"


def load_config() -> dict:
    """
    Load configuration from file, with environment variable fallbacks.

    Priority:
    1. Config file values
    2. Environment variables
    """
    config = {}

    # Load from file if exists
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)

    # Environment variable fallbacks (env vars take precedence if set)
    env_mappings = {
        "subdomain": "RS_SUBDOMAIN",
        "api_key": "RS_API_KEY",
        "include_tickets": "RS_INCLUDE_TICKETS",
        "include_customers": "RS_INCLUDE_CUSTOMERS",
        "include_assets": "RS_INCLUDE_ASSETS",
        "include_invoices": "RS_INCLUDE_INVOICES",
        "include_internal_comments": "RS_INCLUDE_INTERNAL_COMMENTS",
    }

    for config_key, env_var in env_mappings.items():
        env_value = os.environ.get(env_var)
        if env_value is not None:
            # Convert string booleans
            if env_value.lower() in ("true", "1", "yes"):
                config[config_key] = True
            elif env_value.lower() in ("false", "0", "no"):
                config[config_key] = False
            else:
                config[config_key] = env_value

    return config


def save_config(config: dict) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    # Secure the file (contains API key)
    os.chmod(config_path, 0o600)
    print_success(f"Configuration saved to {config_path}")


def cmd_setup(args):
    """Interactive setup wizard."""
    print_banner()
    print(f"{BOLD}Setup Wizard{RESET}")
    print("Let's configure your RepairShopr connection.\n")

    config = load_config()

    # Subdomain
    current = config.get("subdomain", "")
    subdomain = input(f"RepairShopr subdomain [{current}]: ").strip() or current
    if not subdomain:
        print_error("Subdomain is required")
        print("  Example: If your URL is https://acmerepair.repairshopr.com")
        print("  Then your subdomain is: acmerepair")
        return 1

    # API Key
    current = config.get("api_key", "")
    masked = f"{current[:8]}...{current[-4:]}" if len(current) > 12 else "(not set)"
    print(f"\nAPI Key [{masked}]")
    print("  Get it from: RepairShopr → Your Name → Profile → API Tokens")
    api_key = input("API Key (leave empty to keep current): ").strip() or current
    if not api_key:
        print_error("API key is required")
        return 1

    # Options
    print(f"\n{BOLD}Data Options{RESET}")
    include_tickets = input("Include tickets? [Y/n]: ").strip().lower() != 'n'
    include_customers = input("Include customers? [Y/n]: ").strip().lower() != 'n'
    include_assets = input("Include assets? [Y/n]: ").strip().lower() != 'n'
    include_invoices = input("Include invoices? [y/N]: ").strip().lower() == 'y'

    print(f"\n{BOLD}Security Options{RESET}")
    print_warning("Internal comments may contain sensitive information!")
    include_internal = input("Include internal/hidden comments? [y/N]: ").strip().lower() == 'y'

    # Save config
    config = {
        "subdomain": subdomain,
        "api_key": api_key,
        "include_tickets": include_tickets,
        "include_customers": include_customers,
        "include_assets": include_assets,
        "include_invoices": include_invoices,
        "include_internal_comments": include_internal,
    }

    save_config(config)

    # Test connection
    print(f"\n{BOLD}Testing connection...{RESET}")
    return cmd_test(args, config)


def cmd_test(args, config: dict | None = None):
    """Test the RepairShopr connection."""
    if config is None:
        config = load_config()

    if not config.get("subdomain") or not config.get("api_key"):
        print_error("Not configured.")
        print_info("Option 1: Run 'rs-onyx setup' for interactive setup")
        print_info("Option 2: Set environment variables:")
        print(f"    export RS_SUBDOMAIN=yourcompany")
        print(f"    export RS_API_KEY=your-api-key")
        return 1

    print_info(f"Connecting to {config['subdomain']}.repairshopr.com...")

    try:
        from repairshopr_connector.client import RepairShoprClient

        client = RepairShoprClient(
            subdomain=config["subdomain"],
            api_key=config["api_key"],
        )

        with client:
            result = client.health_check()

        if result["status"] == "healthy":
            print_success(f"Connected successfully!")
            print_success(f"Authenticated as: {result.get('user', 'unknown')}")
            return 0
        else:
            print_error(f"Connection failed: {result.get('message', 'Unknown error')}")
            return 1

    except Exception as e:
        print_error(f"Connection failed: {e}")
        return 1


def send_to_onyx(documents: list, onyx_url: str, onyx_api_key: str, verbose: bool = False) -> dict:
    """
    Send documents to Onyx ingestion API.

    Returns dict with success count and errors.
    """
    import httpx

    results = {"success": 0, "failed": 0, "errors": []}

    # Onyx document ingestion endpoint (discovered via /openapi.json)
    endpoint = f"{onyx_url.rstrip('/')}/onyx-api/ingestion"

    headers = {
        "x-onyx-key": onyx_api_key,  # Self-hosted Onyx uses x-onyx-key, not Bearer token
        "Content-Type": "application/json",
    }

    # Log first attempt for debugging
    if verbose or len(documents) > 0:
        print(f"\n{YELLOW}[DEBUG] Onyx endpoint: {endpoint}{RESET}")

    with httpx.Client(timeout=60.0) as client:
        for i, doc in enumerate(documents):
            try:
                # Convert to Onyx format
                payload = {
                    "document": doc.to_dict(),
                }

                response = client.post(endpoint, json=payload, headers=headers)

                if response.status_code in (200, 201):
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    error_msg = f"{doc.id}: HTTP {response.status_code}"
                    results["errors"].append(error_msg)
                    # Log first few errors for debugging
                    if results["failed"] <= 3:
                        print(f"\n{RED}[ERROR] {error_msg}{RESET}")
                        print(f"{RED}[ERROR] Response: {response.text[:200]}{RESET}")

            except Exception as e:
                results["failed"] += 1
                error_msg = f"{doc.id}: {str(e)}"
                results["errors"].append(error_msg)
                if results["failed"] <= 3:
                    print(f"\n{RED}[ERROR] {error_msg}{RESET}")

    return results


def cmd_sync(args):
    """Run a sync to Onyx."""
    config = load_config()

    if not config.get("subdomain") or not config.get("api_key"):
        print_error("Not configured.")
        print_info("Option 1: Run 'rs-onyx setup' for interactive setup")
        print_info("Option 2: Set environment variables:")
        print(f"    export RS_SUBDOMAIN=yourcompany")
        print(f"    export RS_API_KEY=your-api-key")
        return 1

    # Check for Onyx configuration
    onyx_url = os.environ.get("ONYX_API_URL", "")
    onyx_api_key = os.environ.get("ONYX_API_KEY", "")
    send_to_onyx_enabled = bool(onyx_url and onyx_api_key)

    print_banner()
    print(f"{BOLD}Starting Full Sync{RESET}\n")

    if send_to_onyx_enabled:
        print_info(f"Onyx integration enabled: {onyx_url}")
    else:
        print_warning("Onyx not configured - documents will be processed but not sent")
        print_info("Set ONYX_API_URL and ONYX_API_KEY to enable ingestion")
    print()

    try:
        from repairshopr_connector.connector import RepairShoprConnector

        connector = RepairShoprConnector(
            subdomain=config["subdomain"],
            include_tickets=config.get("include_tickets", True),
            include_customers=config.get("include_customers", True),
            include_assets=config.get("include_assets", True),
            include_invoices=config.get("include_invoices", False),
            include_internal_comments=config.get("include_internal_comments", False),
        )

        connector.load_credentials({"api_key": config["api_key"]})

        total_docs = 0
        total_sent = 0
        total_failed = 0

        for batch in connector.load_from_state():
            total_docs += len(batch)

            if send_to_onyx_enabled:
                result = send_to_onyx(batch, onyx_url, onyx_api_key)
                total_sent += result["success"]
                total_failed += result["failed"]
                print(f"\r{BLUE}Documents: {total_docs} | Sent to Onyx: {total_sent} | Failed: {total_failed}{RESET}", end="")
            else:
                print(f"\r{BLUE}Documents processed: {total_docs}{RESET}", end="")

        print(f"\n\n{GREEN}Sync complete!{RESET}")
        print(f"  Documents processed: {total_docs}")
        if send_to_onyx_enabled:
            print(f"  Sent to Onyx: {total_sent}")
            if total_failed > 0:
                print_warning(f"  Failed: {total_failed}")

        stats = connector.get_stats()
        if stats.get("checkpoint"):
            errors = stats["checkpoint"].get("errors", [])
            if errors:
                print_warning(f"  Connector errors: {len(errors)}")
                for err in errors[:5]:
                    print(f"    - {err}")

        return 0

    except Exception as e:
        print_error(f"Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_status(args):
    """Show sync status."""
    print_banner()

    try:
        from repairshopr_connector.state import StateManager

        state_mgr = StateManager()
        checkpoint = state_mgr.load()

        print(f"{BOLD}Sync Status{RESET}\n")

        if checkpoint.last_full_sync:
            print(f"  Last full sync: {checkpoint.last_full_sync.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print_warning("  No full sync completed yet")

        if checkpoint.last_poll:
            print(f"  Last poll: {checkpoint.last_poll.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        if checkpoint.sync_started_at:
            print(f"\n{BOLD}Current/Last Sync:{RESET}")
            print(f"  Type: {checkpoint.sync_type}")
            print(f"  Started: {checkpoint.sync_started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"  Documents: {checkpoint.documents_processed}")

            status = []
            if checkpoint.customers_complete:
                status.append(f"{GREEN}Customers ✓{RESET}")
            if checkpoint.assets_complete:
                status.append(f"{GREEN}Assets ✓{RESET}")
            if checkpoint.tickets_complete:
                status.append(f"{GREEN}Tickets ✓{RESET}")
            if checkpoint.invoices_complete:
                status.append(f"{GREEN}Invoices ✓{RESET}")

            if status:
                print(f"  Completed: {', '.join(status)}")

            if checkpoint.errors:
                print_warning(f"  Errors: {len(checkpoint.errors)}")

        return 0

    except Exception as e:
        print_error(f"Failed to get status: {e}")
        return 1


def cmd_stats(args):
    """Show detailed statistics."""
    config = load_config()

    if not config.get("subdomain"):
        print_error("Not configured. Run 'rs-onyx setup' first.")
        return 1

    print_banner()

    try:
        from repairshopr_connector.connector import RepairShoprConnector

        connector = RepairShoprConnector(subdomain=config["subdomain"])

        if config.get("api_key"):
            connector.load_credentials({"api_key": config["api_key"]})

        stats = connector.get_stats()

        print(f"{BOLD}Connector Statistics{RESET}\n")
        print(f"  Subdomain: {stats['subdomain']}")

        if stats.get("cache"):
            cache = stats["cache"]
            print(f"\n{BOLD}Cache:{RESET}")
            print(f"  Customers: {cache['customers']['size']}/{cache['customers']['max_size']} "
                  f"(hit rate: {cache['customers']['hit_rate']:.1%})")
            print(f"  Assets: {cache['assets']['size']}/{cache['assets']['max_size']} "
                  f"(hit rate: {cache['assets']['hit_rate']:.1%})")

        if stats.get("client"):
            client = stats["client"]
            print(f"\n{BOLD}API Client:{RESET}")
            print(f"  Requests: {client['request_count']}")
            print(f"  Errors: {client['error_count']} ({client['error_rate']:.2%})")

            if client.get("rate_limiter"):
                rl = client["rate_limiter"]
                print(f"  Rate limiter: {rl['requests_made']} requests, "
                      f"{rl['requests_throttled']} throttled, "
                      f"{rl['total_wait_time_seconds']:.1f}s wait time")

        return 0

    except Exception as e:
        print_error(f"Failed to get stats: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="RepairShopr-Onyx Bridge CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rs-onyx setup          Interactive setup wizard
  rs-onyx test           Test your connection
  rs-onyx sync           Run a full sync
  rs-onyx status         Show sync status
  rs-onyx stats          Show statistics

For more information, visit:
  https://github.com/SilverWulf212/Onyx-RS-Bridge
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Setup command
    subparsers.add_parser("setup", help="Interactive setup wizard")

    # Test command
    subparsers.add_parser("test", help="Test your connection")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Run a full sync")
    sync_parser.add_argument("--dry-run", action="store_true", help="Don't actually send to Onyx")

    # Status command
    subparsers.add_parser("status", help="Show sync status")

    # Stats command
    subparsers.add_parser("stats", help="Show statistics")

    args = parser.parse_args()

    if args.command is None:
        print_banner()
        print(f"{BOLD}Quick Start:{RESET}")
        print()
        print("  1. Set your credentials:")
        print(f"     {BLUE}export RS_SUBDOMAIN=yourcompany{RESET}")
        print(f"     {BLUE}export RS_API_KEY=your-api-key{RESET}")
        print()
        print("  2. Test the connection:")
        print(f"     {BLUE}rs-onyx test{RESET}")
        print()
        print("  3. Run a sync:")
        print(f"     {BLUE}rs-onyx sync{RESET}")
        print()
        print(f"{BOLD}Or run 'rs-onyx setup' for interactive configuration.{RESET}")
        print()
        print("Commands:")
        print("  setup   - Interactive setup wizard")
        print("  test    - Test your connection")
        print("  sync    - Run a full sync")
        print("  status  - Show sync status")
        print("  stats   - Show statistics")
        return 0

    commands = {
        "setup": cmd_setup,
        "test": cmd_test,
        "sync": cmd_sync,
        "status": cmd_status,
        "stats": cmd_stats,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
