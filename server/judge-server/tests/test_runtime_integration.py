"""Run inside a disposable judge-server image with JUDGER_RUNTIME_TESTS=1.

Mount backend/judge/languages.py at /audit-languages.py and the SPJ example at
/audit-spj.cpp. No database, network, existing testcase directory, or live token
is used. The normal unprivileged contract suite deliberately skips this class.
"""
import hashlib
import os
from pathlib import Path
import runpy
import sys
import types
import unittest


@unittest.skipUnless(os.environ.get("JUDGER_RUNTIME_TESTS") == "1", "requires disposable judge image")
class JudgeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for directory, mode in (("/judger", 0o755), ("/judger/run", 0o711),
                                ("/judger/spj", 0o711), ("/judger/locks", 0o700)):
            Path(directory).mkdir(parents=True, exist_ok=True)
            os.chmod(directory, mode)
        for name in ("compiler.lock", "file-io.lock"):
            path = Path("/judger/locks", name)
            path.touch(mode=0o600)
        from server import app
        from utils import ProblemIOMode
        # The production language table only needs these protocol constants;
        # importing Django models would unnecessarily require a live database.
        sys.modules["problem.models"] = types.SimpleNamespace(ProblemIOMode=ProblemIOMode)
        cls.languages = {item["name"]: item for item in runpy.run_path("/audit-languages.py")["languages"]}
        cls.client = app.test_client()
        cls.headers = {"X-Judge-Server-Token": hashlib.sha256(os.environ["TOKEN"].encode()).hexdigest()}

    def judge(self, language, code, **options):
        payload = dict(language_config=self.languages[language]["config"], src=code,
                       max_cpu_time=1500, max_memory=256 * 1024 * 1024,
                       test_case=[{"input": "2 3\n", "output": "5\n"}], output=True)
        payload.update(options)
        return self.client.post("/judge", json=payload, headers=self.headers).get_json()

    def test_all_supported_languages_compile_and_run(self):
        sources = {
            "C": '#include <stdio.h>\nint main(){int a,b;scanf("%d%d",&a,&b);printf("%d\\n",a+b);}',
            "C++": '#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b;}',
            "Python3": 'a,b=map(int,input().split());print(a+b)',
            "Java": 'import java.util.*;class Main{public static void main(String[]x){Scanner s=new Scanner(System.in);System.out.println(s.nextInt()+s.nextInt());}}',
            "Golang": 'package main\nimport "fmt"\nfunc main(){var a,b int;fmt.Scan(&a,&b);fmt.Println(a+b)}',
            "JavaScript": 'const fs=require("fs");const a=fs.readFileSync(0,"utf8").trim().split(/\\s+/).map(Number);console.log(a[0]+a[1]);',
        }
        for name, code in sources.items():
            with self.subTest(language=name):
                response = self.judge(name, code)
                self.assertIsNone(response["err"], response)
                self.assertEqual([item["result"] for item in response["data"]], [0], response)

    def test_wrong_answer_compile_error_and_time_limit(self):
        wrong = self.judge("Python3", "print(0)")
        self.assertIsNone(wrong["err"], wrong)
        self.assertEqual(wrong["data"][0]["result"], -1)
        self.assertEqual(self.judge("C", "invalid code")["err"], "CompileError")
        timed = self.judge("C", "int main(){while(1){}}", max_cpu_time=100)
        self.assertIsNone(timed["err"], timed)
        self.assertIn(timed["data"][0]["result"], (1, 2))

    def test_file_io_is_scoped_and_judged(self):
        code = '#include <stdio.h>\nint main(){int a,b;FILE*f=fopen("data.in","r");fscanf(f,"%d%d",&a,&b);fclose(f);f=fopen("data.out","w");fprintf(f,"%d",a+b);fclose(f);}'
        response = self.judge("C", code, io_mode={"io_mode": "File IO", "input": "data.in", "output": "data.out"})
        self.assertIsNone(response["err"], response)
        self.assertEqual(response["data"][0]["result"], 0, response)

    def test_special_judge_accepts_and_rejects_under_real_sandbox(self):
        source = Path("/audit-spj.cpp").read_text()
        options = dict(spj_version=hashlib.md5(source.encode()).hexdigest(), spj_src=source,
                       spj_config=self.languages["C++"]["spj"]["config"],
                       spj_compile_config=self.languages["C++"]["spj"]["compile"],
                       test_case=[{"input": "1\n7\n"}])
        for output, expected in (("4", 0), ("7", -1)):
            with self.subTest(output=output):
                response = self.judge("Python3", f"print({output})", **options)
                self.assertIsNone(response["err"], response)
                self.assertEqual(response["data"][0]["result"], expected, response)

    def test_unauthenticated_request_is_rejected(self):
        self.assertEqual(self.client.post("/ping", json={}).get_json()["err"], "TokenVerificationFailed")


if __name__ == "__main__":
    unittest.main()
