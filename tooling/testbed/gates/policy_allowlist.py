"""
PolicyAllowlist — explicit, visible exception mechanism for Gate 3.

Every exception to a security/policy rule must be declared here.
No silent code branches. This makes known decisions (e.g. netem NET_ADMIN,
otel-collector distroless healthcheck) intentional and auditable.

The default allowlist encodes decisions already made in the QUIC Edge testbed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Risky capabilities registry
# ---------------------------------------------------------------------------

# Capabilities that are considered risky/privilege-escalation vectors.
# These are flagged by Gate 3 unless explicitly allowlisted per-service.
RISKY_CAPABILITIES: set[str] = {
    "SYS_ADMIN",       # Broad admin privileges, namespace manipulation
    "SYS_PTRACE",      # Process inspection, memory access
    "SYS_MODULE",      # Kernel module loading
    "DAC_OVERRIDE",    # Bypass file permission checks
    "DAC_READ_SEARCH", # Bypass file read/search checks
    "SYS_RAWIO",       # Raw I/O, port access
    "SYS_BOOT",        # Reboot
    "SYS_TIME",        # System clock manipulation
    "NET_RAW",         # Raw sockets, packet crafting
    "SYSLOG",          # Kernel dmesg access
    "SYS_RESOURCE",    # Resource limit override
    "IPC_LOCK",        # Memory locking
    "BLOCK_SUSPEND",   # System suspend blocking
}

# Capabilities that are generally safe for network services.
# These are NOT flagged by Gate 3.
SAFE_CAPABILITIES: set[str] = {
    "NET_ADMIN",       # Network configuration (tc, iptables) — needed by netem
    "NET_BIND_SERVICE", # Bind to privileged ports
    "NET_BROADCAST",   # Socket broadcasting
    "CHOWN",           # File ownership changes
    "SETUID",          # Set UID on executables
    "SETGID",          # Set GID on executables
    "SETPCAP",         # Capability setting within permitted set
    "KILL",            # Signal delivery
    "FOWNER",          # Bypass file ownership checks for operations
    "FSETID",          # Set file flags on creation
    "SETFCAP",         # Set file capabilities
    "AUDIT_WRITE",     # Write audit log
    "MKNOD",           # Create device nodes
    "SYS_CHROOT",      # chroot
    "LEASE",           # File lease management
}


# ---------------------------------------------------------------------------
# Sensitive host paths
# ---------------------------------------------------------------------------

# Host paths that are considered sensitive/dangerous to mount into containers.
SENSITIVE_HOST_PATHS: set[str] = {
    "/",
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/var/run/docker.sock",
    "/var/lib/docker",
    "/run/docker.sock",
    "/var/run/docker",
    "/boot",
    "/etc/shadow",
    "/etc/passwd",
    "/etc/ssh",
    "/root",
    "/home",
}

# Docker socket path patterns (checked separately for clearer diagnostics)
DOCKER_SOCKET_PATTERNS: set[str] = {
    "/var/run/docker.sock",
    "/run/docker.sock",
    "/var/run/docker",
}


# ---------------------------------------------------------------------------
# Secret patterns (high-signal only)
# ---------------------------------------------------------------------------

# Environment variable name patterns that suggest secrets
SECRET_ENV_NAME_PATTERNS: list[str] = [
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "auth",
    "credential",
    "private_key",
    "privatekey",
    "access_key",
    "accesskey",
    "secret_key",
    "secretkey",
]

# Value patterns that suggest hardcoded secrets (case-insensitive match)
SECRET_VALUE_PATTERNS: list[str] = [
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
]


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

@dataclass
class PolicyAllowlist:
    """Explicit, visible exception list for Gate 3 security checks.

    Every exception to a security/policy rule must be declared here.
    This makes known decisions intentional and auditable.

    Fields:
        allowed_capabilities: Map of service_name → [capability, ...]
            Capabilities in this list are NOT flagged for the named service.
            Only capabilities in RISKY_CAPABILITIES need allowlisting;
            SAFE_CAPABILITIES are never flagged.

        healthcheck_disabled_services: List of service names where
            healthcheck: disable: true is intentional (e.g. distroless images).

        allowed_privileged_services: List of service names where
            privileged: true is intentional and approved.

        allowed_host_network_services: List of service names where
            network_mode: host is intentional and approved.

        allowed_host_path_mounts: Map of service_name → [host_path, ...]
            Host path mounts that are intentional for the named service.
    """
    allowed_capabilities: dict[str, list[str]] = field(default_factory=dict)
    healthcheck_disabled_services: list[str] = field(default_factory=list)
    allowed_privileged_services: list[str] = field(default_factory=list)
    allowed_host_network_services: list[str] = field(default_factory=list)
    allowed_host_path_mounts: dict[str, list[str]] = field(default_factory=dict)

    def is_capability_allowed(self, service_name: str, capability: str) -> bool:
        """Check if a capability is allowlisted for a service."""
        caps = self.allowed_capabilities.get(service_name, [])
        return capability.upper() in {c.upper() for c in caps}

    def is_healthcheck_disabled_allowed(self, service_name: str) -> bool:
        """Check if a service is allowlisted for healthcheck disable."""
        return service_name in self.healthcheck_disabled_services

    def is_privileged_allowed(self, service_name: str) -> bool:
        """Check if a service is allowlisted for privileged mode."""
        return service_name in self.allowed_privileged_services

    def is_host_network_allowed(self, service_name: str) -> bool:
        """Check if a service is allowlisted for host network mode."""
        return service_name in self.allowed_host_network_services

    def is_host_path_allowed(self, service_name: str, host_path: str) -> bool:
        """Check if a host path mount is allowlisted for a service."""
        allowed = self.allowed_host_path_mounts.get(service_name, [])
        return host_path in allowed


# ---------------------------------------------------------------------------
# Default allowlist (encodes known decisions from the QUIC Edge testbed)
# ---------------------------------------------------------------------------

def default_allowlist() -> PolicyAllowlist:
    """Return the default allowlist encoding known decisions.

    These are decisions already made in the QUIC Edge testbed:
    - netem-router needs NET_ADMIN for tc netem (network emulation)
    - otel-collector uses a distroless image with no shell, so healthcheck
      is intentionally disabled
    """
    return PolicyAllowlist(
        allowed_capabilities={
            "netem-router": ["NET_ADMIN"],
        },
        healthcheck_disabled_services=[
            "otel-collector",
        ],
    )
