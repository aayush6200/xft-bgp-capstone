"""Talk to lab routers: Mac -> lima VM -> docker exec -> vtysh.

The only file that knows routers are containers. Callers hand it a router
name and FRR commands; it returns what the router said. OSPF/BGP layers
reuse it unchanged.

    from xft.drivers.docker import DockerExecDriver
    d = DockerExecDriver()
    print(d.show("ca-ibgp-100", "show ip route"))
    d.configure("ca-ibgp-100", ["interface eth1", "ip address 10.0.0.1/30"])
"""

from __future__ import annotations

import subprocess


class DriverError(RuntimeError):
    pass


class DockerExecDriver:
    def __init__(self, lab: str = "xft", vm: str = "netlab"):
        self.lab = lab
        self.vm = vm

    def _vtysh(self, router: str, commands: list[str]) -> str:
        argv = ["limactl", "shell", self.vm, "--", "sudo", "docker", "exec",
                f"clab-{self.lab}-{router}", "vtysh"]
        for command in commands:
            argv += ["-c", command]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise DriverError(f"{router}: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    def show(self, router: str, command: str) -> str:
        """Run one read-only command, return its output."""
        return self._vtysh(router, [command])

    def exec(self, router: str, argv: list[str]) -> tuple[int, str]:
        """Run an OS-level command (ping, ip, tcpdump ...) in the router's
        container — not through vtysh. Returns (exit_code, output)."""
        cmd = ["limactl", "shell", self.vm, "--", "sudo", "docker", "exec",
               f"clab-{self.lab}-{router}", *argv]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode, result.stdout + result.stderr

    def configure(self, router: str, lines: list[str]) -> str:
        """Apply config lines inside one configure session, then persist them
        so the config survives a container restart (not a redeploy — after a
        redeploy the pipeline is the persistence)."""
        out = self._vtysh(router, ["configure terminal", *lines, "end"])
        self._vtysh(router, ["write memory"])
        return out
