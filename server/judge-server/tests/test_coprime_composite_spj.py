"""Checker regression tests; run with python3 -m unittest discover -s this directory."""
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which("g++"), "g++ is required for the SPJ fixture")
class CoprimeCompositeSPJTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="coprime-spj-")
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.root = Path(cls.workspace.name)
        cls.binary = cls.root / "checker"
        source = Path(__file__).resolve().parents[1] / "examples/spj/coprime_composite.cpp"
        subprocess.run(["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(source), "-o", str(cls.binary)], check=True)

    def verdict(self, input_text, output_text):
        input_file = self.root / "input"
        output_file = self.root / "output"
        input_file.write_text(input_text)
        output_file.write_text(output_text)
        result = subprocess.run([str(self.binary), str(input_file), str(output_file)],
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
        # A checker must not modify the candidate file or rely on printed text
        # as the verdict; the platform uses its process exit status.
        self.assertEqual(output_file.read_text(), output_text)
        self.assertEqual(result.stdout, b"")
        return result.returncode

    def test_accepts_distinct_valid_constructions(self):
        for output in ("15\n35\n77\n", "9\n49\n961\n", "+9 +49 +961 \n"):
            with self.subTest(output=output):
                self.assertEqual(self.verdict("3\n2\n6\n30\n", output), 0)

    def test_rejects_invalid_values_and_missing_or_extra_tokens(self):
        for output in ("", "0", "1", "-9", "2", "7", "6", "15 35",
                       "15 garbage", "15.0", "15garbage", "+", "18446744073709551616"):
            with self.subTest(output=output):
                self.assertEqual(self.verdict("1\n2\n", output), 1)
        self.assertEqual(self.verdict("3\n2\n6\n30\n", "15 35"), 1)

    def test_reads_each_answer_from_the_candidate_file(self):
        self.assertEqual(self.verdict("3\n2\n6\n30\n", "15 35 49"), 0)
        self.assertEqual(self.verdict("3\n2\n6\n30\n", "15 35 7"), 1)

    def test_small_values_match_independent_trial_division(self):
        for answer in range(2, 250):
            prime = all(answer % d for d in range(2, math.isqrt(answer) + 1))
            expected = 0 if not prime and math.gcd(answer, 97) == 1 else 1
            with self.subTest(answer=answer):
                self.assertEqual(self.verdict("1\n97\n", str(answer)), expected)

    def test_large_composites_and_primes(self):
        for answer in (1000000002000000001, 1000000016000000063,
                       341550071728321, 3825123056546413051, 18446744073709551615):
            with self.subTest(composite=answer):
                self.assertEqual(self.verdict("1\n2\n", str(answer)), 0)
        for answer in (1000000007, 2305843009213693951, 18446744073709551557):
            with self.subTest(prime=answer):
                self.assertEqual(self.verdict("1\n2\n", str(answer)), 1)

    def test_maximum_batch_of_large_valid_answers(self):
        self.assertEqual(self.verdict("100000\n" + "1000000000\n" * 100000,
                                      "1000000002000000001\n" * 100000), 0)

    def test_bad_invocation_and_test_input_are_checker_errors(self):
        result = subprocess.run([str(self.binary)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        for input_text in ("", "0\n", "100001\n", "1\n1\n", "2\n2\n", "1\n2\nextra"):
            with self.subTest(input_text=input_text):
                self.assertEqual(self.verdict(input_text, "15 35" if input_text == "2\n2\n" else "15"), 2)


if __name__ == "__main__":
    unittest.main()
