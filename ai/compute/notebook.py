"""Bounded, reusable Jupyter kernels. Idle student containers are frozen."""
import hashlib
import json
import re
import selectors
import subprocess
import tempfile
import time
import uuid


class NotebookExecutor:
    def __init__(self, image, engine="docker", *, owner="notebook-tests", max_kernels=3,
                 memory_mb=1024, idle_seconds=600):
        self.image, self.engine, self.owner = image, engine, owner
        self.max_kernels, self.memory_mb, self.idle_seconds = int(max_kernels), int(memory_mb), int(idle_seconds)
        if not (1 <= self.max_kernels <= 32 and 256 <= self.memory_mb <= 4096 and 30 <= self.idle_seconds <= 3600):
            raise ValueError("Invalid Notebook pool limits")
        self.sessions = {}

    def preflight(self):
        subprocess.run([self.engine, "info", "--format", "{{.ServerVersion}}"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        subprocess.run([self.engine, "image", "inspect", self.image], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

    def recover(self):
        # Only on owner startup, never from a read-only preflight invocation.
        names = subprocess.check_output([self.engine, "ps", "-aq", "--filter", "label=org.xju.ai=notebook",
                                         "--filter", "label=org.xju.ai.notebook-owner=" + self.owner],
                                        text=True, timeout=15).split()
        if names:
            subprocess.run([self.engine, "rm", "-f", *names], check=True, timeout=20,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def drop(self, key):
        session = self.sessions.get(key)
        if not session:
            return
        process = session["process"]
        try:
            subprocess.run([self.engine, "rm", "-f", session["name"]], timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            del self.sessions[key]
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            session["errors"].close()

    def close(self):
        for key in list(self.sessions):
            self.drop(key)

    def reap_idle(self):
        for key, session in list(self.sessions.items()):
            if time.monotonic() - session["last_used"] > self.idle_seconds or session["process"].poll() is not None:
                self.drop(key)

    def start(self, key):
        while len(self.sessions) >= self.max_kernels:
            self.drop(min(self.sessions, key=lambda item: self.sessions[item]["last_used"]))
        name = "xju-notebook-" + hashlib.sha256(self.owner.encode()).hexdigest()[:8] + "-" + key
        command = [self.engine, "run", "--name", name, "--label", "org.xju.ai=notebook", "-i",
                   "--label", "org.xju.ai.notebook-owner=" + self.owner,
                   "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                   "--user=65532:65532", "--pids-limit=128", "--cpus=2",
                   "--memory=" + str(self.memory_mb) + "m", "--memory-swap=" + str(self.memory_mb) + "m",
                   "--ulimit", "nofile=256:256", "--ulimit", "core=0", "--log-driver=none",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,uid=65532,gid=65532,mode=700",
                   "--tmpfs", "/work:rw,nosuid,nodev,size=256m,uid=65532,gid=65532,mode=700",
                   "--workdir=/work", "--env=HOME=/work", "--env=OMP_NUM_THREADS=2", "--env=MPLCONFIGDIR=/work/.mpl",
                   "--env=HTTP_PROXY=", "--env=HTTPS_PROXY=", "--env=ALL_PROXY=", "--env=http_proxy=", "--env=https_proxy=",
                   self.image, "python", "-I", "/opt/xju/notebook_runner.py"]
        errors = tempfile.TemporaryFile()
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        except Exception:
            errors.close()
            raise
        session = {"name": name, "process": process, "errors": errors, "generation": uuid.uuid4().hex,
                   "last_used": time.monotonic(), "paused": False}
        self.sessions[key] = session
        return session

    def run(self, job, heartbeat):
        self.reap_idle()
        payload = job["payload"]
        persistent = bool(payload.get("kernel_id"))
        key = payload.get("kernel_id") or uuid.UUID(job["id"]).hex
        if not re.fullmatch(r"[0-9a-f]{32,64}", key):
            raise ValueError("Invalid kernel identity")
        session = self.sessions.get(key) or self.start(key)
        # A finish response can be lost after execution. Reclaiming that job must
        # not apply a stateful cell twice in the same kernel.
        if session.get("completed_job") == job["id"]:
            return session["result"]
        process, errors = session["process"], session["errors"]
        reset = bool(payload.get("kernel_generation") and payload["kernel_generation"] != session["generation"]
                     and payload.get("cell_index") is not None)
        seconds = max(5, min(600, int(job["judge"].get("run_seconds", 120))))
        result = {"status": "SYSTEM_ERROR"}
        cells = []
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer = bytearray()
        received = frames = 0
        started = last_heartbeat = time.monotonic()
        last_progress = 0
        dirty = False
        try:
            if session["paused"]:
                subprocess.run([self.engine, "unpause", session["name"]], check=True, timeout=10,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                session["paused"] = False
            errors.seek(0)
            errors.truncate()
            command = {"cells": payload["cells"], "files": payload.get("files", {}), "seconds": seconds,
                       "cell_index": payload.get("cell_index"), "reset_only": reset}
            process.stdin.write(json.dumps(command).encode() + b"\n")
            process.stdin.flush()
            complete = False
            while not complete:
                if time.monotonic() - started > seconds + 45:
                    result = {"status": "TIME_LIMIT"}
                    break
                if errors.tell() > 256 * 1024:
                    break
                for event, _ in selector.select(timeout=0.5):
                    chunk = event.fileobj.read1(65536)
                    if not chunk:
                        complete = True
                        break
                    received += len(chunk)
                    buffer.extend(chunk)
                    if received > 8 * 1024 * 1024 or len(buffer) > 3 * 1024 * 1024:
                        raise ValueError("Notebook output limit exceeded")
                    while b"\n" in buffer:
                        line, _, remainder = buffer.partition(b"\n")
                        buffer = bytearray(remainder)
                        frame = json.loads(line)
                        frames += 1
                        if frames > 2 * len(payload["cells"]) + 2 or not isinstance(frame, dict):
                            raise ValueError("Invalid Notebook stream")
                        if frame.get("event") == "start":
                            cells = frame["output"]["cells"]
                            if len(cells) != len(payload["cells"]):
                                raise ValueError("Invalid cell count")
                            dirty = True
                        elif frame.get("event") == "cell":
                            index = frame.get("index")
                            if type(index) is not int or not 0 <= index < len(cells) or not isinstance(frame.get("cell"), dict):
                                raise ValueError("Invalid cell progress")
                            cells[index] = frame["cell"]
                            dirty = True
                        elif frame.get("event") == "result":
                            result = {"status": frame["status"], "output": frame["output"]}
                            complete = True
                        else:
                            raise ValueError("Unknown Notebook event")
                stamp = time.monotonic()
                if not complete and dirty and stamp - last_progress >= 0.5:
                    heartbeat(output={"cells": cells, "kernel_id": session["generation"]})
                    dirty = False
                    last_progress = last_heartbeat = stamp
                elif not complete and stamp - last_heartbeat >= 15:
                    heartbeat()
                    last_heartbeat = stamp
            inspected = subprocess.run([self.engine, "inspect", "--format", "{{.State.OOMKilled}}", session["name"]],
                                       capture_output=True, text=True, timeout=10)
            if inspected.stdout.strip() == "true":
                result = {"status": "MEMORY_LIMIT"}
            output = result.setdefault("output", {"cells": cells})
            output["kernel_id"] = session["generation"]
            if reset:
                output["kernel_reset"] = True
            if result["status"] not in ("SUCCEEDED", "RUNTIME_ERROR", "CANCELLED"):
                self.drop(key)
            elif persistent and process.poll() is None:
                # Freeze all student threads between executions, not just the main thread.
                subprocess.run([self.engine, "pause", session["name"]], check=True, timeout=10,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                session["paused"] = True
                session["last_used"] = time.monotonic()
                session["completed_job"], session["result"] = job["id"], result
            else:
                self.drop(key)
            return result
        except BaseException:
            self.drop(key)
            raise
        finally:
            selector.close()
