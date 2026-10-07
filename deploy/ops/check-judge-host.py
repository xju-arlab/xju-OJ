#!/usr/bin/env python3
"""Reject hosts that cannot enforce the judge's file write boundary."""
import ctypes
import os
import platform
import sys


def probe_landlock_abi():
    # These are the Linux architectures supported by our image toolchains.
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise RuntimeError("the judge requires a supported Linux host")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    # landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION).
    # This read-only query needs neither root nor an installed judge image.
    abi = libc.syscall(ctypes.c_long(444), ctypes.c_void_p(),
                       ctypes.c_size_t(0), ctypes.c_uint(1))
    if abi < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return int(abi)


def main():
    try:
        abi = probe_landlock_abi()
        if abi < 3:
            raise RuntimeError(f"Landlock ABI {abi} is below the required ABI 3")
    except (OSError, RuntimeError) as error:
        print(f"Judge host preflight failed: {error}. Java and File IO require "
              "Landlock ABI >= 3. On Ubuntu 22.04, install the official HWE "
              "6.8 kernel and reboot before deployment; do not disable sandboxing.",
              file=sys.stderr)
        return 1
    print(f"Judge host preflight passed: Landlock ABI {abi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
