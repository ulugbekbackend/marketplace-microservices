"""payme-simulator [--gateway URL] [--key KEY] [scenario ...]"""

import argparse
import sys

from decouple import config

from payme_simulator import SCENARIOS, run


def main() -> None:
    parser = argparse.ArgumentParser(prog="payme-simulator", description=__doc__)
    parser.add_argument("scenarios", nargs="*", metavar="scenario", help=", ".join(SCENARIOS))
    parser.add_argument("--gateway", default=config("GATEWAY_URL", default="http://127.0.0.1"))
    parser.add_argument("--key", default=config("PAYME_KEY", default=""))
    args = parser.parse_args()
    unknown = set(args.scenarios) - set(SCENARIOS)
    if unknown:
        parser.error(f"unknown scenario: {', '.join(sorted(unknown))}")
    if not args.key:
        parser.error("PAYME_KEY is empty: set it in .env or pass --key")
    report = run(args.gateway, args.key, args.scenarios or None)
    print(report.render())
    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
