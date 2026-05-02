"""Discovery helpers for ``meridian chat --dev`` frontend launchers."""

from __future__ import annotations

import json
import shutil
import subprocess


def is_portless_available() -> bool:
    """Return whether the ``portless`` executable is available on ``PATH``."""

    return shutil.which("portless") is not None


def detect_tailscale_dns_name() -> str | None:
    """Return this node's Tailscale MagicDNS name, if it can be detected."""

    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        dns_name = data.get("Self", {}).get("DNSName")
        if not isinstance(dns_name, str) or not dns_name:
            return None
        return dns_name.rstrip(".")
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        return None


def get_portless_url(name: str) -> str | None:
    """Get the stable URL for a portless-managed service."""

    try:
        result = subprocess.run(
            ["portless", "get", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def get_portless_tailscale_url(name: str) -> str | None:
    """Get the tailscale URL for a portless route by parsing ``portless list``."""

    try:
        result = subprocess.run(
            ["portless", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    # Parse output like:
    #   https://app.meridian.localhost:1355  ->  localhost:4568  (pid 123)
    #     tailscale: https://pop-os.tail852a76.ts.net:8444
    found_route = False
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if f"{name}.localhost" in stripped and "->" in stripped:
            found_route = True
        elif found_route and stripped.startswith("tailscale:"):
            return stripped.split("tailscale:", 1)[1].strip()
        elif found_route and stripped and "->" in stripped:
            # Next route — stop searching
            break
    return None
