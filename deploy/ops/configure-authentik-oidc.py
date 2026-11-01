#!/usr/bin/env python3
"""Write the OJ Authentik OIDC settings from a protected two-line stream.

In a TTY it prompts for the client ID and hidden client secret. In a
non-interactive invocation stdin must contain exactly two lines: the client ID
and the client secret. The secret is never accepted as an argument, environment
variable, or log value. The pipe mode is intended for a root-to-root SSH pipe
from the Authentik host.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import stat
import sys
import tempfile
from pathlib import Path


CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def fail(message: str) -> "NoReturn":
    print(f"configure-oidc: {message}", file=sys.stderr)
    raise SystemExit(1)


def atomic_write(path: Path, content: str, mode: int, uid: int, gid: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
            os.fchown(handle.fileno(), uid, gid)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def update_env(path: Path, values: dict[str, str]) -> None:
    if not path.is_file() or path.is_symlink():
        fail(f"env file is missing or is a symlink: {path}")
    original = path.stat()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    key_re = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*?)(\r?\n)?$")
    locations: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = key_re.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in locations:
            fail(f"duplicate environment key: {key}")
        locations[key] = index
    for key, value in values.items():
        if "\n" in value or "\r" in value or "\x00" in value:
            fail(f"invalid value for {key}")
        if key in locations:
            line = lines[locations[key]]
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            lines[locations[key]] = f"{key}={value}{ending}"
        else:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += "\n"
            lines.append(f"{key}={value}\n")
    atomic_write(path, "".join(lines), stat.S_IMODE(original.st_mode), original.st_uid, original.st_gid)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--secret-file", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.env_file.is_absolute() or not args.secret_file.is_absolute():
        fail("paths must be absolute")
    if sys.stdin.isatty():
        print("Enter the xju-OJ provider values locally; the secret will not be displayed")
        client_id = input("Client ID: ").strip()
        client_secret = getpass.getpass("Client secret (hidden): ")
    else:
        client_id = sys.stdin.readline().rstrip("\r\n")
        client_secret = sys.stdin.readline().rstrip("\r\n")
        if sys.stdin.readline() != "":
            fail("unexpected extra credential input")
    if not CLIENT_ID_RE.fullmatch(client_id):
        fail("invalid client ID")
    if len(client_secret) < 16 or any(char in client_secret for char in "\r\n\x00"):
        fail("invalid client secret")
    secret_path = args.secret_file.resolve(strict=False)
    if args.secret_file.is_symlink():
        fail("secret file must not be a symlink")
    secret_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if secret_path.exists() and not secret_path.is_file():
        fail("secret path is not a regular file")
    atomic_write(secret_path, client_secret + "\n", 0o600, os.getuid(), os.getgid())
    update_env(
        args.env_file,
        {
            "AUTHENTIK_OIDC_ENABLED": "true",
            "AUTHENTIK_LOCAL_LOGIN_ENABLED": "false",
            "AUTHENTIK_LOCAL_REGISTER_ENABLED": "false",
            "AUTHENTIK_OIDC_ISSUER": "https://auth.icthub.top/application/o/xju-oj/",
            "AUTHENTIK_OIDC_CLIENT_ID": client_id,
            "AUTHENTIK_OIDC_CLIENT_SECRET_FILE": str(secret_path),
            "AUTHENTIK_OIDC_REDIRECT_URI": "https://oj.icthub.top/api/auth/oidc/callback/",
            "AUTHENTIK_OIDC_REGISTER_URL": "https://auth.icthub.top/if/flow/icthub-xju-oj-registration/",
            "AUTHENTIK_OIDC_SCOPES": "openid profile email groups",
        },
    )
    print("Authentik OIDC settings installed; local login/register are disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
