"""Bounded Docker execution for the pinned upstream Codabench compute worker.

This module changes the container and archive boundaries; upstream still schedules,
executes ingestion/scoring separately, and records all official scores.
"""
import asyncio
import io
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

import docker
import compute_worker as upstream

app = upstream.app
MAX_BUNDLE = 32 * 1024 * 1024
MAX_RESULTS = 16 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Bundle redirects are disabled")


def storage_url(url):
    url = upstream.rewrite_bundle_url_if_needed(url)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme + "://" + parsed.netloc != os.environ["CODABENCH_STORAGE_ORIGIN"]:
        raise ValueError("Unapproved bundle origin")
    return url


def bounded_extract(content, destination):
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(content)) as bundle:
        entries = bundle.infolist()
        if len(entries) > 256 or sum(item.file_size for item in entries) > MAX_BUNDLE:
            raise ValueError("Bundle limits exceeded")
        for item in entries:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or stat.S_ISLNK(mode):
                raise ValueError("Unsafe archive member")
            output = target.joinpath(*path.parts)
            if item.is_dir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("xb") as stream:
                    stream.write(bundle.read(item))


def safe_archive(directory):
    root = Path(directory)
    buffer = io.BytesIO()
    size = count = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for parent, dirs, files in os.walk(root, followlinks=False):
            if any(Path(parent, name).is_symlink() for name in dirs):
                raise ValueError("Symbolic directories are not results")
            for name in files:
                path = Path(parent, name)
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    count += 1
                    size += info.st_size
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or count > 64 or size > MAX_RESULTS:
                        raise ValueError("Unsafe or excessive result files")
                    content = stream.read(MAX_RESULTS + 1)
                    if len(content) > MAX_RESULTS:
                        raise ValueError("Result grew beyond its limit")
                    bundle.writestr(path.relative_to(root).as_posix(), content)
    return buffer.getvalue()


def get_bundle(self, url, destination, cache=False):
    url = storage_url(url)
    with urllib.request.build_opener(NoRedirect).open(url, timeout=30) as response:
        content = response.read(MAX_BUNDLE + 1)
    if len(content) > MAX_BUNDLE:
        raise ValueError("Bundle is too large")
    bounded_extract(content, os.path.join(self.root_dir, destination))
    Path(self.bundle_dir).mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=self.bundle_dir, delete=False) as stream:
        stream.write(content)
        return stream.name


def put_dir(self, url, directory):
    self._put_file(url, raw_data=safe_archive(directory))


def put_file(self, url, file=None, raw_data=None, content_type="application/zip"):
    url = storage_url(url)
    stream = open(file, "rb") if file else None
    try:
        response = self.requests_session.put(url, data=stream if stream else raw_data,
                                             headers={"Content-Type": content_type}, timeout=(5, 30), allow_redirects=False)
        if response.is_redirect:
            raise ValueError("Result redirects are disabled")
        response.raise_for_status()
    finally:
        if stream:
            stream.close()


def create_container(self, container_name, command, volumes_host, volumes_config):
    if self.container_image != os.environ["XJU_EVALUATION_IMAGE"]:
        raise ValueError("Unapproved evaluation image")
    binds = {}
    for source, config in volumes_config.items():
        target = config["bind"]
        if target == "/app/data":
            continue  # Never mount the worker's shared data directory into student code.
        if target not in {"/app/program", "/app/output", "/app/ingested_program", "/app/input", "/app/input_data", "/app/shared"}:
            raise ValueError("Unexpected container mount")
        relative = os.path.relpath(source, upstream.Settings.HOST_DIRECTORY)
        if relative.startswith(".."):
            raise ValueError("Mount escaped worker workspace")
        writable = target in ("/app/output", "/app/shared")
        if writable:
            local = Path(upstream.Settings.BASE_DIR, relative)
            if local.is_symlink():
                raise ValueError("Unsafe output directory")
            local.mkdir(parents=True, exist_ok=True)
            os.chown(local, 65532, 65532)
            os.chmod(local, 0o700)
        binds[source] = {"bind": target, "mode": "rw" if writable else "ro"}
    config = upstream.client.create_host_config(
        cap_drop=["ALL"], security_opt=["no-new-privileges"], read_only=True,
        network_mode="none", mem_limit="1536m", memswap_limit="1536m", nano_cpus=1000000000,
        pids_limit=128, binds=binds, tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m,uid=65532,gid=65532,mode=700"},
        log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
        ulimits=[docker.types.Ulimit(name="core", soft=0, hard=0), docker.types.Ulimit(name="nofile", soft=256, hard=256)],
    )
    return upstream.client.create_container(self.container_image, name=container_name, command=command,
                                            host_config=config, user="65532:65532", working_dir="/app/program",
                                            environment={"HOME": "/tmp", "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1",
                                                         "PYTHONUNBUFFERED": "1"}, network_disabled=True)


async def run_container(self, container, kind):
    """Collect logs even when a short process exits before Docker attach starts."""
    started = time.time()
    stdout = stderr = b""
    code = 1
    try:
        upstream.client.start(container)
        result = await asyncio.to_thread(upstream.client.wait, container, timeout=self.execution_time_limit + 5)
        code = result["StatusCode"]
        if upstream.client.inspect_container(container)["State"].get("OOMKilled"):
            self.xju_failure = "XJU_MEMORY_LIMIT"
        # Docker's one-file 1 MiB ring bounds memory here, even for a noisy process.
        stdout = upstream.client.logs(container, stdout=True, stderr=False)
        stderr = upstream.client.logs(container, stdout=False, stderr=True)
        if len(stdout) + len(stderr) > 65536:
            code = 1
            stdout, stderr = b"", b"Output limit exceeded"
    finally:
        try:
            upstream.client.remove_container(container, v=True, force=True)
        except docker.errors.NotFound:
            pass  # The upstream wall-clock watchdog may already have removed it.
        scoring = kind == upstream.ProgramKind.SCORING_PROGRAM
        self.logs[kind] = {"returncode": code, "start": started, "end": time.time(),
            "stdout": {"data": stdout, "stream": stdout, "continue": True,
                       "location": self.stdout if scoring else self.ingestion_stdout},
            "stderr": {"data": stderr, "stream": stderr, "continue": True,
                       "location": self.stderr if scoring else self.ingestion_stderr}}
        self.completed_program_counter += 1


upstream_update_status = upstream.Run._update_status


def update_status(self, status, extra_information=""):
    # The pinned upstream checks scoring's return code, but not ingestion's.
    # Fail before uploading incomplete artifacts and requesting scoring.
    # Publishing SCORING itself schedules the next task; reject the transition
    # before it is sent, so a later scoring failure cannot overwrite the cause.
    if (status == upstream.SubmissionStatus.SCORING and not self.is_scoring and self.ingestion_program_data
            and getattr(self, "ingestion_program_exit_code", None) != 0):
        raise upstream.SubmissionException(getattr(self, "xju_failure", "XJU_RUNTIME_ERROR"))
    return upstream_update_status(self, status, extra_information)


async def no_browser_socket(self, data):
    # OJ uses authenticated REST results. This private WSGI deployment has no
    # Codabench browser WebSocket; notification failure must not replace a TLE.
    return None


# Method names are checked against the pinned upstream when building and in integration tests.
upstream.Run._get_bundle = get_bundle
upstream.Run._put_dir = put_dir
upstream.Run._put_file = put_file
upstream.Run._create_container = create_container
upstream.Run._run_container_engine_cmd = run_container
upstream.Run._update_status = update_status
upstream.Run._send_data_through_socket = no_browser_socket
