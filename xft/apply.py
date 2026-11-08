"""Push interface addresses to the lab from intent/topology.yml.

    python -m xft.apply --dry-run   # print the address table, touch nothing
    python -m xft.apply             # configure every router in scope
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from xft.drivers.docker import DockerExecDriver, DriverError
from xft.render.addresses import assignments, config_lines
from xft.render.clab import apply_scope, load_intent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", default="mvp")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    intent = apply_scope(load_intent(), args.scope)

    by_router: dict[str, list] = defaultdict(list)
    for a in assignments(intent):
        by_router[a.router].append(a)

    if args.dry_run:
        for router, assigned in by_router.items():
            for a in assigned:
                print(f"{router:<16} {a.interface:<6} {a.address}")
        return 0

    driver = DockerExecDriver()
    failed = 0
    for router, assigned in by_router.items():
        try:
            driver.configure(router, config_lines(assigned))
            got = driver.show(router, "show interface brief")
            print(f"{router}: pushed {len(assigned)} addresses")
        except DriverError as err:
            print(f"{router}: FAILED — {err}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
