"""Derive interface addresses from the topology.

Rule (from the design doc, recorded in topology.yml): in each /30 the
source end takes the first usable address, the destination the second.
Loopbacks are taken verbatim from each router's entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_network


@dataclass(frozen=True)
class Assignment:
    router: str
    interface: str
    address: str  # e.g. "10.0.0.1/30"


def assignments(intent: dict) -> list[Assignment]:
    out: list[Assignment] = []

    for link in intent["links"]:
        net = ip_network(link["subnet"])
        first, second = list(net.hosts())
        out.append(Assignment(link["source"]["router"], link["source"]["interface"],
                              f"{first}/{net.prefixlen}"))
        out.append(Assignment(link["destination"]["router"], link["destination"]["interface"],
                              f"{second}/{net.prefixlen}"))

    for router in intent["routers"]:
        if router.get("loopback"):
            out.append(Assignment(router["name"], "lo", router["loopback"]))

    return out


def config_lines(per_router: list[Assignment]) -> list[str]:
    """FRR config lines for one router's assignments."""
    lines: list[str] = []
    for a in per_router:
        lines += [f"interface {a.interface}", f"ip address {a.address}", "exit"]
    return lines
