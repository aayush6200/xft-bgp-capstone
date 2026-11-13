"""Talk to lab routers from the Mac: limactl -> docker exec -> vtysh.

This is the TRANSPORT layer. It knows how to reach a router and deliver
text; it knows nothing about OSPF, BGP, or addressing. Renderers build the
lines, this file carries them. If we ever swap containerlab for real
hardware, only this file changes.

Three public methods, one per kind of conversation:

    show(router, command)      one read-only FRR command   -> output string
    configure(router, lines)   config lines, then persist  -> output string
    exec(router, argv)         an OS command (ping, ip...) -> (exit_code, output)

Typical use from a renderer:

    from xft.drivers.docker import DockerExecDriver, DriverError

    driver = DockerExecDriver()
    driver.configure("ca-abr-100", ["router ospf", " ospf router-id 10.255.0.11"])
    print(driver.show("ca-abr-100", "show ip ospf neighbor"))
"""

from __future__ import annotations

import subprocess


class DriverError(RuntimeError):
    """Raised when a router could not be reached or rejected a command.

    The message always starts with the router's name, followed by whatever
    the failing layer printed (docker, vtysh, or FRR itself). Catch this
    when one router failing should not abort a loop over all of them.
    """


class DockerExecDriver:
    """Reaches containerlab routers via `limactl shell` + `docker exec`.

    Every call builds the full command chain from scratch, so there is no
    session state to manage: no connections to open, keep alive, or close.

    Attributes:
        lab: containerlab topology name; containers are named
            ``clab-<lab>-<router>``, so lab="xft" + router="ca-abr-100"
            targets the container ``clab-xft-ca-abr-100``.
        vm: name of the Lima VM the lab runs inside.
    """

    def __init__(self, lab: str = "xft", vm: str = "netlab") -> None:
        self.lab = lab
        self.vm = vm

    # ------------------------------------------------------------------ #
    # internal plumbing                                                  #
    # ------------------------------------------------------------------ #

    def _vtysh(self, router: str, commands: list[str]) -> str:
        """Run one vtysh invocation on one router.

        Each string in ``commands`` becomes its own ``-c`` argument, and
        vtysh executes them in order within a single session — so config
        context carries across them ("configure terminal" affects the
        lines that follow), exactly like typing them one by one.

        Args:
            router: router name as it appears in topology.yml
                (e.g. "ca-abr-100" — without the "clab-xft-" prefix).
            commands: vtysh commands, executed in order.

        Returns:
            Everything the commands printed (stdout), as one string.

        Raises:
            DriverError: non-zero exit from any layer (unknown container,
                vtysh parse error, FRR refusing a command).
            subprocess.TimeoutExpired: no answer within 30 seconds.
        """
        argv = ["limactl", "shell", self.vm, "--", "sudo", "docker", "exec",
                f"clab-{self.lab}-{router}", "vtysh"]
        for command in commands:
            argv += ["-c", command]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise DriverError(f"{router}: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    # ------------------------------------------------------------------ #
    # public interface — what renderers call                             #
    # ------------------------------------------------------------------ #

    def show(self, router: str, command: str) -> str:
        """Run one read-only command and return what the router printed.

        Args:
            router: router name, e.g. "ca-ibgp-100".
            command: a single FRR show/clear-style command,
                e.g. "show ip ospf neighbor".

        Returns:
            The command's output as a string. Parse it or print it;
            nothing on the router changed.

        Example:
            >>> driver.show("ca-ibgp-100", "show ip route")
        """
        return self._vtysh(router, [command])
    

    def get_loopback_address(self, router: str, command: str = 'show interface lo') -> str:
        """
        Get the routers loopback lo
        Args:
            router: router name, e.g. "ca-ibgp-100"
            command: a single FRR show/clear-style command to get the router loopback, default show interface loopback

        """
        lines = self.show(router, command)
        output_lines = lines.splitlines()

        for line in output_lines:
            line = line.strip()
            if line.startswith('inet'):
                addr = line.split()[1].split("/")[0]
                return addr


    def configure(self, router: str, lines: list[str]) -> str:
        """Apply configuration lines, then persist them.

        The lines are wrapped in one session:
        ``configure terminal`` ... your lines ... ``end``, followed by a
        separate ``write memory`` so the config survives a container
        restart. (Not a redeploy — after a redeploy, re-running the
        pipeline IS the persistence.)

        Indentation in the lines is cosmetic; vtysh tracks context from
        the commands themselves, so ``"interface eth1"`` followed by
        ``"ip ospf area 100"`` lands the area command on eth1.

        Args:
            router: router name, e.g. "ca-abr-100".
            lines: config commands in order, WITHOUT "configure terminal"
                or "end" — this method adds those.

        Returns:
            Output printed during the config session (usually empty;
            FRR complains loudly and that surfaces as DriverError).

        Raises:
            DriverError: if the session or the save failed.

        Example:
            >>> driver.configure("ca-abr-100", [
            ...     "router ospf",
            ...     " ospf router-id 10.255.0.11",
            ...     "exit",
            ...     "interface eth1",
            ...     " ip ospf area 100",
            ... ])
        """
        out = self._vtysh(router, ["configure terminal", *lines, "end"])
        self._vtysh(router, ["write memory"])
        return out

    def exec(self, router: str, argv: list[str]) -> tuple[int, str]:
        """Run an OS-level command inside the router's container.

        For anything that is not an FRR command: ping, ip, traceroute,
        tcpdump. Runs directly in the container, bypassing vtysh.

        Unlike show/configure, this does NOT raise on failure — a failed
        ping is a result, not an error. Check the exit code yourself.

        Args:
            router: router name, e.g. "ok-border-000".
            argv: the command as a list, one element per word,
                e.g. ["ping", "-c", "2", "-W", "1", "10.0.0.1"].

        Returns:
            (exit_code, output): exit_code is 0 on success; output is
            stdout and stderr combined.

        Example:
            >>> code, out = driver.exec("ca-ibgp-100", ["ping", "-c", "2", "10.0.0.2"])
            >>> reachable = (code == 0)
        """
        cmd = ["limactl", "shell", self.vm, "--", "sudo", "docker", "exec",
               f"clab-{self.lab}-{router}", *argv]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode, result.stdout + result.stderr
