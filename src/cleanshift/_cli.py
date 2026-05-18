"""CLI entry point: ``cleanshift schedule ...``"""

import argparse
import sys
from datetime import datetime, timezone


def _parse_duration_hours(value: str) -> float:
    """Parse '2h', '30m', '90s' into fractional hours."""
    value = value.strip()
    if value.endswith("h"):
        return float(value[:-1])
    if value.endswith("m"):
        return float(value[:-1]) / 60.0
    if value.endswith("s"):
        return float(value[:-1]) / 3600.0
    return float(value)  # bare number treated as hours


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="cleanshift",
        description="Find or schedule the cleanest grid window for a batch job.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sched = sub.add_parser("schedule", help="Print the recommended start time.")
    sched.add_argument("--duration", default="1h", metavar="DURATION",
                       help="Expected job duration (e.g. 2h, 30m). Default: 1h")
    sched.add_argument("--max-delay", default="24h", metavar="DELAY",
                       help="Maximum acceptable delay (e.g. 24h). Default: 24h")
    sched.add_argument("--region", default="MOCK", metavar="REGION",
                       help="Grid region label (e.g. US-CAL-CISO). Default: MOCK")
    sched.add_argument("--provider", default="mock",
                       choices=["mock", "electricitymap", "watttime"],
                       help="Data provider. Default: mock")
    sched.add_argument("--api-key", metavar="KEY",
                       help="API key (ElectricityMap).")
    sched.add_argument("--zone", metavar="ZONE",
                       help="Zone override for ElectricityMap (defaults to --region).")
    sched.add_argument("--username", metavar="USER",
                       help="Username (WattTime).")
    sched.add_argument("--password", metavar="PASS",
                       help="Password (WattTime).")
    sched.add_argument("--dry-run", action="store_true",
                       help="Print recommendation without executing anything.")

    args = parser.parse_args(argv)

    if args.command == "schedule":
        try:
            duration_hours = _parse_duration_hours(args.duration)
            max_delay_hours = _parse_duration_hours(args.max_delay)
        except ValueError as exc:
            parser.error(str(exc))
            return

        if args.provider == "mock":
            from cleanshift.providers.mock import MockProvider
            provider = MockProvider(region=args.region)

        elif args.provider == "electricitymap":
            if not args.api_key:
                parser.error("--api-key is required for the electricitymap provider")
            from cleanshift.providers.electricitymap import ElectricityMapProvider
            provider = ElectricityMapProvider(
                api_key=args.api_key,
                zone=args.zone or args.region,
            )

        elif args.provider == "watttime":
            if not (args.username and args.password):
                parser.error("--username and --password are required for the watttime provider")
            from cleanshift.providers.watttime import WattTimeProvider
            provider = WattTimeProvider(
                username=args.username,
                password=args.password,
                region=args.region,
            )

        from cleanshift.scheduler import find_cleanest_window

        best_time = find_cleanest_window(
            provider,
            duration_hours=duration_hours,
            max_delay_hours=max_delay_hours,
        )

        now = datetime.now(tz=timezone.utc)
        delay_s = max(0.0, (best_time - now).total_seconds())
        delay_h = int(delay_s // 3600)
        delay_m = int((delay_s % 3600) // 60)

        print(f"Provider : {provider.provider_name}")
        print(f"Region   : {provider.region}")
        print(f"Duration : {args.duration}")
        print(f"Max delay: {args.max_delay}")
        print()
        print(f"Recommended start : {best_time.isoformat()}")
        if delay_s < 60:
            print("Delay             : now (already in a clean window)")
        else:
            print(f"Delay             : {delay_h}h {delay_m}m from now")

        if not args.dry_run:
            print()
            print("(Pass --dry-run to suppress this note.)")


if __name__ == "__main__":
    main()
