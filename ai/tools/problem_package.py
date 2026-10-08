"""Build/validate portable AI problem data outside the application source tree."""
import argparse
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from ai_studio.package_format import MAX_EXPANDED, MAX_MEMBER, MAX_MEMBERS, MAX_UPLOAD, PackageError, make_zip, parse_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("archive", type=Path)
    build = sub.add_parser("build")
    build.add_argument("directory", type=Path)
    build.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "validate":
            with args.archive.open("rb") as stream:
                raw = stream.read(MAX_UPLOAD + 1)
        else:
            root = args.directory.resolve(strict=True)
            if not root.is_dir():
                raise PackageError("Source must be a directory")
            files, size = {}, 0
            for path in sorted(root.rglob("*")):
                mode = path.lstat().st_mode
                if stat.S_ISDIR(mode):
                    continue
                if not stat.S_ISREG(mode):
                    raise PackageError("Links and special files are not allowed")
                if path.stat().st_size > MAX_MEMBER:
                    raise PackageError("Member exceeds 16 MiB")
                content = path.read_bytes(); size += len(content)
                files[path.relative_to(root).as_posix()] = content
                if size > MAX_EXPANDED or len(files) > MAX_MEMBERS:
                    raise PackageError("Package exceeds size/file-count limit")
            raw = make_zip(files)
        problems = parse_package(raw)
        if args.action == "build":
            # Never overwrite an existing author's archive.
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush(); os.fsync(stream.fileno())
        print("Valid package:", len(problems), "problem(s)")
        for item in problems:
            print(item["metadata"]["type"], item["metadata"]["title"])
    except (PackageError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
