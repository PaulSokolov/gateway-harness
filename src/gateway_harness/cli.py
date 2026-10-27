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
        "--meta-showcase",
        action="store_true",
        help="Run end-to-end Meta Hackathon Muse Wonder -> Spark/Llama showcase",
    )
    demo_parser.add_argument(
        "--chaos", type=str, metavar="POLICY_ID", help="Inject chaos regression to trigger tripwire"
    )

    # client command
    client_parser = subparsers.add_parser("client", help="Run enterprise client traffic generator")
    client_parser.add_argument("--count", type=int, default=15, help="Number of requests")
    client_parser.add_argument("--rps", type=float, default=2.0, help="Target requests per second")
    client_parser.add_argument("--model", default="meta/muse-wonder", help="Target enterprise model")
    client_parser.add_argument("--gateway", default="http://localhost:4000", help="Gateway base URL")
    client_parser.add_argument("--key", default="sk-test-master-key", help="Gateway master/client API key")

    args = parser.parse_args()
    settings = get_settings()

    if args.command == "report":
        cfg_path = args.config
        if not cfg_path.exists():
            # Check local fallback
            local_fallback = Path(__file__).resolve().parents[2] / "config" / "litellm.yaml"
            if local_fallback.exists():
                cfg_path = local_fallback

        ledger_dir = settings.resolved_data_dir / "ledger"
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

        ledger_dir = settings.resolved_data_dir / "ledger"
        store = LedgerStore(ledger_dir, read_only=False)

        if args.fast_forward:
            count = seed_demo_traffic(store, total_requests=300)
            print(f"✨ Fast-forward complete! Seeded {count} requests across 10 simulated days.")
            print("Run 'gh report' or visit http://localhost:8000 to see identified clusters and savings!")

        if args.meta_showcase:
            import asyncio

            from gateway_harness.demo.meta_showcase import run_meta_hackathon_showcase

            asyncio.run(
                run_meta_hackathon_showcase(
                    data_dir=settings.resolved_data_dir,
                    db_url=settings.DATABASE_URL,
                )
            )

        if args.chaos:
            import asyncio

            disabled = asyncio.run(inject_quality_degradation(store, policy_id=args.chaos))
            print(f"🚨 Chaos injected! Circuit breaker evaluated and disabled: {disabled}")
        store.close()

    elif args.command == "client":
        import asyncio

        from gateway_harness.demo.enterprise_client import run_enterprise_traffic

        print(f"🚀 Firing enterprise workload ({args.count} requests) to {args.gateway}...")
        results = asyncio.run(
            run_enterprise_traffic(
                gateway_url=args.gateway,
                api_key=args.key,
                count=args.count,
                rps=args.rps,
                model=args.model,
            )
        )
        succeeded = sum(1 for r in results if r.get("status_code") == 200)
        routed = sum(1 for r in results if r.get("scaffold_applied"))
        print(f"\nDone: {succeeded}/{len(results)} successful calls. Scaffolded/routed: {routed}.")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
