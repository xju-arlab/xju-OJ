"""A partial deployment must not make an old backend image appear current."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class ComponentRevisionTest(unittest.TestCase):
    def test_reuse_compares_component_revision_not_last_deployment_revision(self):
        source = (Path(__file__).resolve().parents[2] / "deploy.sh").read_text()
        functions = []
        for start, end in (("release_source_commit() {", "release_image_ref() {"),
                           ("target_paths() {", "target_ref_for() {"),
                           ("target_unchanged_since_release() {", "set_target_ref_from_release() {")):
            functions.append(start + source.split(start, 1)[1].split(end, 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-C", directory, *args], text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Isolated test")
            git("config", "user.email", "test@example.invalid")
            (root / "backend").mkdir()
            (root / "backend/app.py").write_text("old")
            git("add", ".")
            git("commit", "-qm", "initial")
            previous = git("rev-parse", "HEAD")
            (root / "backend/app.py").write_text("changed")
            git("commit", "-qam", "backend changed")
            current = git("rev-parse", "HEAD")
            with tempfile.NamedTemporaryFile(mode="w") as release:
                json.dump({"source_commit": current, "images": {
                    "backend": {"source_commit": previous}, "frontend": {"source_commit": current}
                }}, release)
                release.flush()
                script = '\n'.join(functions) + '\nROOT=$1\nrelease_file=$2\ntarget_unchanged_since_release "$3"\n'
                def unchanged(target):
                    return subprocess.run(["sh", "-c", script, "revision-test", directory, release.name, target],
                                          capture_output=True, text=True, timeout=10)
                self.assertEqual(unchanged("frontend").returncode, 0)
                self.assertNotEqual(unchanged("backend").returncode, 0)
