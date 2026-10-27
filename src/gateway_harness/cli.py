from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gateway_harness.funnel.report import format_report_markdown, generate_report
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="gh", description="Gateway Harness Appliance CLI")
    subparsers = parser.add_subparsers(dest="command")

    # report command
    rep_parser = subparsers.add_parser("report", help="Generate Savings Opportunity Report")
    rep_parser.add_argument("--format", choices=["md", "json"], default="md", help="Output format")
    rep_parser.add_argument("--window", type=int, default=30, help="Lookback window in days")
    rep_parser.add_argument(
        "--config",
        type=Path,
        default=Path("/app/config/litellm.yaml"),
        help="Path to LiteLLM configuration file",
    )

    # demo command
    demo_parser = subparsers.add_parser("demo", help="Meta Hackathon interactive demo runner")
    demo_parser.add_argument(
        "--fast-forward", action="store_true", help="Fast-forward 10 days of simulated production traces"
    )
    demo_parser.add_argument(
        "--chaos", type=str, metavar="POLICY_ID", help="Inject chaos regression to trigger tripwire"
    )

    args = parser.parse_args()
    settings = get_settings()

    if args.command == "report":
        cfg_path = args.config
        if not cfg_path.exists():
            # Check local fallback
            local_fallback = Path(__file__).resolve().parents[2] / "config" / "litellm.yaml"
            if local_fallback.exists():
                cfg_path = local_fallback

        ledger_dir = settings.DATA_DIR / "ledger"
        store = LedgerStore(ledger_dir, read_only=True)
        report_data = generate_report(store, cfg_path, settings, window_days=args.window)
        store.close()

        if args.format == "json":
            print(json.dumps(report_data, indent=2))
        else:
            print(format_report_markdown(report_data))

    elif args.command == "demo":
        from gateway_harness.demo.chaos import inject_quality_degradation
        from gateway_harness.demo.fast_forward import seed_demo_traffic

        ledger_dir = settings.DATA_DIR / "ledger"
        store = LedgerStore(ledger_dir, read_only=False)

        if args.fast_forward:
            count = seed_demo_traffic(store, total_requests=300)
            print(f"✨ Fast-forward complete! Seeded {count} requests across 10 simulated days.")
            print("Run 'gh report' or visit http://localhost:8000 to see identified clusters and savings!")

        if args.chaos:
            import asyncio

            disabled = asyncio.run(inject_quality_degradation(store, policy_id=args.chaos))
            print(f"🚨 Chaos injected! Circuit breaker evaluated and disabled: {disabled}")
        store.close()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
