"""Execute a fresh Jupyter kernel in a bounded container. No student host mounts."""
import json
import selectors
import subprocess
import tempfile
import time


class NotebookExecutor:
    def __init__(self, image, engine="docker"):
        self.image = image
        self.engine = engine

    def preflight(self):
        # Refuse an unavailable engine; there is deliberately no local Python fallback.
        subprocess.run([self.engine, "info", "--format", "{{.ServerVersion}}"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        subprocess.run([self.engine, "image", "inspect", self.image], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

    def run(self, job, heartbeat):
        name = "xju-notebook-" + job["id"] + "-" + job["lease"][:8]
        seconds = max(5, min(600, int(job["judge"].get("run_seconds", 120))))
        command = [self.engine, "run", "--name", name, "--label", "org.xju.ai=notebook", "-i",
                   "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                   "--user=65532:65532", "--pids-limit=128", "--cpus=2", "--memory=2g", "--memory-swap=2g",
                   "--ulimit", "nofile=256:256", "--ulimit", "core=0", "--log-driver=none",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,uid=65532,gid=65532,mode=700",
                   "--tmpfs", "/work:rw,nosuid,nodev,size=256m,uid=65532,gid=65532,mode=700",
                   "--workdir=/work", "--env=HOME=/work", "--env=OMP_NUM_THREADS=2", "--env=MPLCONFIGDIR=/work/.mpl",
                   "--env=HTTP_PROXY=", "--env=HTTPS_PROXY=", "--env=ALL_PROXY=", "--env=http_proxy=", "--env=https_proxy=",
                   self.image, "python", "-I", "/opt/xju/notebook_runner.py"]
        result = {"status": "SYSTEM_ERROR"}
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as errors:
            source.write(json.dumps({"cells": job["payload"]["cells"], "files": job["payload"].get("files", {}), "seconds": seconds}).encode())
            source.seek(0)
            process = subprocess.Popen(command, stdin=source, stdout=subprocess.PIPE, stderr=errors)
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            output = bytearray()
            started = last_heartbeat = time.monotonic()
            try:
                while selector.get_map():
                    elapsed = time.monotonic() - started
                    if elapsed > seconds + 45:
                        result = {"status": "TIME_LIMIT"}
                        break
                    if time.monotonic() - last_heartbeat >= 15:
                        heartbeat()
                        last_heartbeat = time.monotonic()
                    if errors.tell() > 256 * 1024:
                        break
                    for key, _ in selector.select(timeout=1):
                        chunk = key.fileobj.read1(65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        output.extend(chunk)
                        if len(output) > 3 * 1024 * 1024:
                            raise ValueError("Notebook output limit exceeded")
                else:
                    code = process.wait(timeout=5)
                    # A kernel can be OOM-killed while nbclient survives and reports
                    # a timeout. Docker's cgroup OOM event takes precedence.
                    inspected = subprocess.run([self.engine, "inspect", "--format", "{{.State.OOMKilled}}", name],
                                               capture_output=True, text=True, timeout=10)
                    if inspected.stdout.strip() == "true":
                        result = {"status": "MEMORY_LIMIT"}
                    elif code == 0:
                        result = json.loads(output)
                    else:
                        result = {"status": "RUNTIME_ERROR"}
            finally:
                selector.close()
                subprocess.run([self.engine, "rm", "-f", name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=15)
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                process.stdout.close()
        return result
