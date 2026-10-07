import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid

from flask import Flask, request, Response

from compiler import Compiler
from config import (COMPILER_GROUP_GID, COMPILER_LOCK_PATH,
                    JUDGER_WORKSPACE_BASE, RUN_GROUP_GID, SPJ_EXE_DIR,
                    SPJ_GROUP_GID, SPJ_SRC_DIR, TEST_CASE_DIR)
from exception import TokenVerificationFailed, CompileError, SPJCompileError, JudgeClientError
from judge_client import JudgeClient
from utils import (ProblemIOMode, logger, open_root_lock, server_info,
                   token)

app = Flask(__name__)
DEBUG = os.environ.get("judger_debug") == "1"
app.debug = DEBUG


def handoff_compiled_artifact(path, group_gid, force_executable=False):
    file_stat = os.lstat(path)
    if stat.S_ISLNK(file_stat.st_mode):
        raise JudgeClientError("compiler produced a symbolic link")

    if stat.S_ISDIR(file_stat.st_mode):
        os.chown(path, 0, group_gid, follow_symlinks=False)
        os.chmod(path, 0o550)
        for entry in os.scandir(path):
            handoff_compiled_artifact(entry.path, group_gid)
    elif stat.S_ISREG(file_stat.st_mode):
        if file_stat.st_nlink != 1:
            raise JudgeClientError("compiler produced a multiply linked artifact")
        os.chown(path, 0, group_gid, follow_symlinks=False)
        executable = force_executable or bool(stat.S_IMODE(file_stat.st_mode) & 0o111)
        os.chmod(path, 0o550 if executable else 0o440)
    else:
        raise JudgeClientError("compiler produced an unsupported artifact")


def handoff_compiled_artifacts(output_dir, group_gid, excluded_paths=()):
    # Compiler outputs become root-owned and immutable to the runtime UID. This
    # prevents parallel test cases from changing a shared executable or class.
    excluded_paths = set(excluded_paths)
    for entry in os.scandir(output_dir):
        if entry.path not in excluded_paths:
            handoff_compiled_artifact(entry.path, group_gid)
    # Root retains write access to create testcase directories; the runtime
    # group may only traverse/read artifacts, and other sandbox users only get
    # traversal for a testcase-local SPJ directory.
    os.chown(output_dir, 0, group_gid)
    os.chmod(output_dir, 0o751)


def is_regular_single_link(path):
    try:
        file_stat = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISREG(file_stat.st_mode) and file_stat.st_nlink == 1


def require_leaf_name(value, field):
    if not isinstance(value, str) or not value or value in (".", "..") or os.path.basename(value) != value:
        raise JudgeClientError("invalid %s" % field)
    return value


def prepare_cleanup_tree(path):
    # The compiler/runtime users may own nested bytecode or output directories.
    # Never chown a multiply linked regular file: unlinking the local directory
    # entry is sufficient and must not mutate an inode outside this tree.
    for entry in os.scandir(path):
        file_stat = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(file_stat.st_mode):
            os.chown(entry.path, 0, 0, follow_symlinks=False)
            os.chmod(entry.path, 0o700)
            prepare_cleanup_tree(entry.path)
        elif stat.S_ISREG(file_stat.st_mode) and file_stat.st_nlink == 1:
            os.chown(entry.path, 0, 0, follow_symlinks=False)


class InitSubmissionEnv(object):
    def __init__(self, judger_workspace, submission_id, init_test_case_dir=False):
        self.work_dir = os.path.join(judger_workspace, submission_id)
        self.init_test_case_dir = init_test_case_dir
        if init_test_case_dir:
            self.test_case_dir = os.path.join(self.work_dir, "submission_" + submission_id)
        else:
            self.test_case_dir = None

    def __enter__(self):
        try:
            os.mkdir(self.work_dir)
            os.chmod(self.work_dir, 0o700)
            os.chown(self.work_dir, 0, 0)
            if self.init_test_case_dir:
                os.mkdir(self.test_case_dir)
                # Inline expected outputs stay root-only. The native launcher
                # opens stdin before dropping privileges; File IO and SPJ use
                # root-created testcase-local copies.
                os.chmod(self.test_case_dir, 0o700)
                os.chown(self.test_case_dir, 0, 0)
        except Exception as e:
            logger.exception(e)
            raise JudgeClientError("failed to create runtime dir")
        return self.work_dir, self.test_case_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not DEBUG:
            try:
                prepare_cleanup_tree(self.work_dir)
                shutil.rmtree(self.work_dir)
            except Exception as e:
                logger.exception(e)
                raise JudgeClientError("failed to clean runtime dir")


class JudgeServer:
    @classmethod
    def ping(cls):
        data = server_info()
        data["action"] = "pong"
        return data

    @classmethod
    def judge(cls, language_config, src, max_cpu_time, max_memory, test_case_id=None, test_case=None,
              spj_version=None, spj_config=None, spj_compile_config=None, spj_src=None, output=False,
              io_mode=None):
        if not io_mode:
            io_mode = {"io_mode": ProblemIOMode.standard}

        if not (test_case or test_case_id) or (test_case and test_case_id):
            raise JudgeClientError("invalid parameter")
        if io_mode.get("io_mode") == ProblemIOMode.file:
            input_name = require_leaf_name(io_mode.get("input"), "input filename")
            output_name = require_leaf_name(io_mode.get("output"), "output filename")
            if (input_name == output_name or
                    input_name in {".judger-stdio", ".spj"} or
                    output_name in {".judger-stdio", ".spj"}):
                raise JudgeClientError("invalid file IO configuration")
        # init
        compile_config = language_config.get("compile")
        if compile_config:
            compile_config = dict(compile_config)
            compile_config["src_name"] = require_leaf_name(
                compile_config["src_name"], "source name")
            compile_config["exe_name"] = require_leaf_name(
                compile_config["exe_name"], "executable name")
        run_config = language_config["run"]
        submission_id = uuid.uuid4().hex

        is_spj = spj_version and spj_config

        if is_spj:
            spj_exe_name = require_leaf_name(
                spj_config["exe_name"].format(spj_version=spj_version), "SPJ executable name")
            spj_exe_path = os.path.join(SPJ_EXE_DIR, spj_exe_name)
            # spj src has not been compiled
            if not is_regular_single_link(spj_exe_path):
                logger.warning("%s does not exists, spj src will be recompiled")
                cls.compile_spj(spj_version=spj_version, src=spj_src,
                                spj_compile_config=spj_compile_config)

        init_test_case_dir = bool(test_case)
        with InitSubmissionEnv(JUDGER_WORKSPACE_BASE, submission_id=str(submission_id), init_test_case_dir=init_test_case_dir) as dirs:
            submission_dir, test_case_dir = dirs
            if test_case_dir is None:
                test_case_id = require_leaf_name(str(test_case_id), "test case id")
                test_case_dir = os.path.join(TEST_CASE_DIR, test_case_id)

            if compile_config:
                src_path = os.path.join(submission_dir, compile_config["src_name"])

                # write source code into file
                with open(src_path, "w", encoding="utf-8") as f:
                    f.write(src)
                os.chmod(src_path, 0o440)
                os.chown(src_path, 0, COMPILER_GROUP_GID)

                # All compiler invocations use one fixed UID. Take the global
                # exclusive lock so that compiler-owned paths cannot overlap a
                # concurrently running submission before artifact handoff.
                with open_root_lock(COMPILER_LOCK_PATH) as compiler_lock:
                    fcntl.flock(compiler_lock.fileno(), fcntl.LOCK_EX)
                    # Pending workspaces stay root-only until every earlier
                    # compiler has exited and its artifacts are sealed.
                    os.chown(submission_dir, 0, COMPILER_GROUP_GID)
                    os.chmod(submission_dir, 0o770)
                    exe_path = Compiler().compile(compile_config=compile_config,
                                                  src_path=src_path,
                                                  output_dir=submission_dir)
                    # Java may create Main.class instead of the logical exe path;
                    # hand off the complete compiler tree as immutable artifacts.
                    handoff_compiled_artifacts(
                        submission_dir, RUN_GROUP_GID,
                        excluded_paths=(test_case_dir,) if test_case_dir else (),
                    )
            else:
                run_exe_name = require_leaf_name(run_config["exe_name"], "runtime source name")
                exe_path = os.path.join(submission_dir, run_exe_name)
                with open(exe_path, "w", encoding="utf-8") as f:
                    f.write(src)
                handoff_compiled_artifact(exe_path, RUN_GROUP_GID, force_executable=True)
                os.chown(submission_dir, 0, RUN_GROUP_GID)
                os.chmod(submission_dir, 0o751)

            if init_test_case_dir:
                info = {"test_case_number": len(test_case), "spj": is_spj, "test_cases": {}}
                # write test case
                for index, item in enumerate(test_case):
                    index += 1
                    item_info = {}

                    input_name = str(index) + ".in"
                    item_info["input_name"] = input_name
                    input_data = item["input"].encode("utf-8")
                    item_info["input_size"] = len(input_data)

                    with open(os.path.join(test_case_dir, input_name), "wb") as f:
                        f.write(input_data)
                    if not is_spj:
                        output_name = str(index) + ".out"
                        item_info["output_name"] = output_name
                        output_data = item["output"].encode("utf-8")
                        item_info["output_md5"] = hashlib.md5(output_data).hexdigest()
                        item_info["output_size"] = len(output_data)
                        item_info["stripped_output_md5"] = hashlib.md5(output_data.rstrip()).hexdigest()

                        with open(os.path.join(test_case_dir, output_name), "wb") as f:
                            f.write(output_data)
                    info["test_cases"][index] = item_info
                with open(os.path.join(test_case_dir, "info"), "w") as f:
                    json.dump(info, f)

            judge_client = JudgeClient(run_config=language_config["run"],
                                       exe_path=exe_path,
                                       max_cpu_time=max_cpu_time,
                                       max_memory=max_memory,
                                       test_case_dir=test_case_dir,
                                       submission_dir=submission_dir,
                                       spj_version=spj_version,
                                       spj_config=spj_config,
                                       output=output,
                                       io_mode=io_mode)
            run_result = judge_client.run()

            return run_result

    @classmethod
    def compile_spj(cls, spj_version, src, spj_compile_config):
        if not isinstance(src, str):
            raise SPJCompileError("invalid SPJ source")

        compile_config = dict(spj_compile_config)
        if ("{spj_version}" not in compile_config["src_name"] or
                "{spj_version}" not in compile_config["exe_name"]):
            raise SPJCompileError("SPJ artifact names must include the version")
        compile_config["src_name"] = require_leaf_name(
            compile_config["src_name"].format(spj_version=spj_version), "SPJ source name")
        compile_config["exe_name"] = require_leaf_name(
            compile_config["exe_name"].format(spj_version=spj_version), "SPJ executable name")
        if compile_config["src_name"] == compile_config["exe_name"]:
            raise SPJCompileError("SPJ source and executable names conflict")

        spj_src_path = os.path.join(SPJ_SRC_DIR, compile_config["src_name"])
        spj_exe_path = os.path.join(SPJ_EXE_DIR, compile_config["exe_name"])

        # A version is immutable once published. Compile in a private directory,
        # hand off permissions there, then publish source and executable using
        # same-filesystem atomic renames so judges never observe a partial file.
        with open(os.path.join(SPJ_EXE_DIR, ".compile.lock"), "a") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            if os.path.lexists(spj_exe_path):
                if (not is_regular_single_link(spj_exe_path) or
                        not is_regular_single_link(spj_src_path)):
                    raise SPJCompileError("invalid published SPJ artifact")
                with open(spj_src_path, encoding="utf-8") as source_file:
                    if source_file.read() != src:
                        raise SPJCompileError("SPJ version already exists with different source")
                return "success"

            staging_dir = tempfile.mkdtemp(prefix=".compile-", dir=SPJ_EXE_DIR)
            try:
                os.chown(staging_dir, 0, 0)
                os.chmod(staging_dir, 0o700)
                staged_src_path = os.path.join(staging_dir, compile_config["src_name"])
                with open(staged_src_path, "x", encoding="utf-8") as source_file:
                    source_file.write(src)
                os.chmod(staged_src_path, 0o440)
                os.chown(staged_src_path, 0, SPJ_GROUP_GID)

                try:
                    with open_root_lock(COMPILER_LOCK_PATH) as compiler_lock:
                        fcntl.flock(compiler_lock.fileno(), fcntl.LOCK_EX)
                        os.chown(staging_dir, 0, SPJ_GROUP_GID)
                        os.chmod(staging_dir, 0o770)
                        staged_exe_path = Compiler().compile(
                            compile_config=compile_config,
                            src_path=staged_src_path,
                            output_dir=staging_dir,
                            compiler_group_gid=SPJ_GROUP_GID,
                        )
                        handoff_compiled_artifact(
                            staged_exe_path, SPJ_GROUP_GID, force_executable=True)
                        if not is_regular_single_link(staged_exe_path):
                            raise SPJCompileError("compiler produced invalid SPJ executable")
                except CompileError as e:
                    raise SPJCompileError(e.message)

                os.chown(staged_src_path, 0, 0)
                os.chmod(staged_src_path, 0o400)
                os.replace(staged_src_path, spj_src_path)
                os.replace(staged_exe_path, spj_exe_path)
            finally:
                prepare_cleanup_tree(staging_dir)
                shutil.rmtree(staging_dir)
        return "success"


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=["POST"])
def server(path):
    if path in ("judge", "ping", "compile_spj"):
        _token = request.headers.get("X-Judge-Server-Token")
        try:
            if _token != token:
                raise TokenVerificationFailed("invalid token")
            try:
                data = request.json
            except Exception:
                data = {}
            ret = {"err": None, "data": getattr(JudgeServer, path)(**data)}
        except (CompileError, TokenVerificationFailed, SPJCompileError, JudgeClientError) as e:
            logger.exception(e)
            ret = {"err": e.__class__.__name__, "data": e.message}
        except Exception as e:
            logger.exception(e)
            ret = {"err": "JudgeClientError", "data": e.__class__.__name__ + " :" + str(e)}
    else:
        ret = {"err": "InvalidRequest", "data": "404"}
    return Response(json.dumps(ret), mimetype='application/json')


if DEBUG:
    logger.info("DEBUG=ON")

# gunicorn -w 4 -b 0.0.0.0:8080 server:app
if __name__ == "__main__":
    app.run(debug=DEBUG)
