"""click-simulator [--gateway URL] [--service-id ID] [--secret KEY] [scenario ...]"""

import argparse
import sys

from decouple import config

from click_simulator import SCENARIOS, run


def main() -> None:
    parser = argparse.ArgumentParser(prog="click-simulator", description=__doc__)
    parser.add_argument("scenarios", nargs="*", metavar="scenario", help=", ".join(SCENARIOS))
    parser.add_argument("--gateway", default=config("GATEWAY_URL", default="http://127.0.0.1"))
    parser.add_argument("--service-id", default=config("CLICK_SERVICE_ID", default=""))
    parser.add_argument("--secret", default=config("CLICK_SECRET_KEY", default=""))
    args = parser.parse_args()
    unknown = set(args.scenarios) - set(SCENARIOS)
    if unknown:
        parser.error(f"unknown scenario: {', '.join(sorted(unknown))}")
    if not args.service_id or not args.secret:
        parser.error("CLICK_SERVICE_ID / CLICK_SECRET_KEY are empty: set them in .env")
    report = run(args.gateway, args.service_id, args.secret, args.scenarios or None)
    print(report.render())
    sys.exit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
