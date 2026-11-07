# Build plan — from design doc to running network

The design lives in `docs/` (currently v2.4). This file tracks how it gets built.

## Principle

One source of truth in `intent/`, everything else generated. The link table in
the design doc carries three things — who connects to what, the /30 on each end,
and the OSPF area per interface. The containerlab file consumes only the first.
The other two feed the router configs. Hand-maintaining those separately is how
a cable ends up plugged into an interface no one configured.

## Pipeline

```
intent/*.yml → validate → render → plan (diff vs running) → apply → verify
```

## Phases

| # | Phase | Deliverable | Status |
|---|---|---|---|
| 0 | Foundations | repo skeleton, link table as YAML, validation catching duplicate subnets / interface typos | in progress |
| 1 | Topology | `lab/xft.clab.yaml` — 15 nodes, 22 links, deployed and cabled | |
| 2 | OSPF | per-router interface + OSPF config, pushed; gate on all adjacencies Full | |
| 3 | iBGP | 2 RRs, 8 clients, 17 sessions; gate on Established with expected PfxRcd | |
| 4 | eBGP + policy | 12 partner sessions; non-transit outbound filter **generated**, not typed | |
| 5 | Verify / drift | parse `show ... json`, compare to intent, non-zero exit on drift | |
| 6 | CI | GitHub Actions: validate + render + unit tests on every PR | |

## Build scope — MVP first (design doc v2.5)

`intent/topology.yml` always describes the full target. A **scope** says which
part to build now, and names routers only — a link is in scope when both its
routers are, so adding a router pulls in its cables automatically.

`mvp` = **10 routers, 11 links**: 3 site routers, 3 ABRs, one reflector
(ok-core-000), one border router (b1), and one partner on each side (A, X).
Single points of failure accepted; every address for the missing pieces is
already reserved, so nothing renumbers when they arrive.

```
.venv/bin/python -m xft.render.clab               # mvp
.venv/bin/python -m xft.render.clab --scope full  # the whole target
```

Growing it is one line in `scopes.mvp.routers` at a time: add `ok-border-001`
and its seven cables appear; add `b-ebgp-65002` and its link to b1 appears.

## Open — must be answered before the layer that needs them

| Open | Blocks |
|---|---|
| Second RR: name, loopback, cabling | phase 3 |
| XFT's own prefixes | phase 4 (the outbound permit line) |
| What lives in core areas 100/200/300 besides the site router | phase 2 |
| Department area routers and cabling | later |

Writing these as YAML schema fields is itself a forcing function: a validator
will not accept `loopback: ?`.

## Hard problems worth naming

**Idempotency.** FRR config reload is additive — removing a line from a file does
not remove it from the router. `frr-reload.py` (ships inside the FRR container)
diffs running against target and emits the `no` commands. That is `terraform apply`.

**Phase ordering.** iBGP sessions ride loopbacks, so OSPF must converge before
iBGP can establish. Apply is not one shot; it is phased with health gates that
read real protocol state between layers.

## Tooling

Python + Jinja2 + Pydantic + pytest. Nornir later for parallel execution.
GitHub Actions for CI. StackStorm deliberately deferred — its value is
event-driven remediation, which is the last phase, not the first.
