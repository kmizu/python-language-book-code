"""Chapter snapshots run in isolation, without access to later implementations."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ChapterStageTests(unittest.TestCase):
    def execute(self, stage, script=None):
        snapshot = ROOT / "chapters" / stage
        self.assertTrue(snapshot.is_dir(), f"chapter {stage} snapshot is missing")
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for source in snapshot.glob("*.py"):
                shutil.copyfile(source, work / source.name)
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            command = [sys.executable, "-X", "utf8"]
            command += ["run.py"] if script is None else ["-c", script]
            result = subprocess.run(command, cwd=work, env=env,
                                    capture_output=True, text=True,
                                    encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def evaluate(self, stage, source, output, globals):
        script = (
            "import json\nfrom frontend import parse_program\n"
            "from interpreter import Interpreter\n"
            f"result = Interpreter(parse_program({source!r})).run()\n"
            "print(json.dumps([result.output, result.globals]))\n"
        )
        self.assertEqual(json.loads(self.execute(stage, script)), [output, globals])

    def rejects(self, stage, sources):
        script = (
            "from frontend import parse_program, ParseError\n"
            f"sources = {sources!r}\n"
            "for source in sources:\n"
            "    try:\n        parse_program(source)\n"
            "    except (ParseError, ValueError):\n        pass\n"
            "    else:\n        raise AssertionError(source)\n"
        )
        self.execute(stage, script)

    def test_04_arithmetic_names_comments_and_assignment(self):
        self.evaluate("04", "# price\nlet price=80; let total=100+price*3; "
                      "total=total-(+20)*2; total;", [],
                      {"price": 80, "total": 300})

    def test_04_rejects_print_branches_comparisons_loops_and_functions(self):
        self.rejects("04", ["print 1;", "if 1 { let x=1; }", "1<2;",
                            "1==2;", "while 1 { 1; }",
                            "fn f(x) { return x; }", "f(1);"])

    def test_05_print_and_zero_nonzero_branches_share_environment(self):
        self.evaluate("05", "let x=1; if 0 { x=99; } else { x=x+2; } "
                      "if -1 { let y=x*2; print y; } else {} print x; 7;",
                      [6, 3], {"x": 3, "y": 6})

    def test_05_rejects_comparisons_loops_and_functions(self):
        self.rejects("05", ["print 1<2;", "print 1==2;", "while 1 {}",
                            "fn f(x) { return x; }", "f(1);", "return 1;"])

    def test_06_comparisons_are_integer_zero_or_one(self):
        self.evaluate("06", "print 1<2; print 2<=2; print 3>4; "
                      "print 4>=4; print 5==5; print 6!=6; print (1<2)+4;",
                      [1, 1, 0, 1, 1, 0, 5], {})

    def test_06_loops_update_shared_environment_and_nested_blocks(self):
        self.evaluate("06", "let i=0; let total=0; while i<4 { "
                      "if i!=2 { total=total+i; } else {} i=i+1; } "
                      "while 0 { total=99; } print total; print i;",
                      [4, 4], {"i": 4, "total": 4})

    def test_06_rejects_chained_comparisons_and_functions(self):
        self.rejects("06", ["print 1<2<3;", "print 1==2!=3;",
                            "fn f(x) { return x; }", "f(1);", "return 1;"])

    def test_07_recursive_functions_keep_local_frames_independent(self):
        self.evaluate("07", "fn factorial(n) { if n<=1 { return 1; } "
                      "return n*factorial(n-1); } "
                      "let n=99; print factorial(6); print n;",
                      [720, 99], {"n": 99})

    def test_07_rejects_invalid_function_and_return_forms(self):
        self.rejects("07", ["return 1;", "fn f(x,x) { return x; }",
                            "fn f() {} fn f() {}", "print 1<2<3;"])

    def test_each_stage_defines_its_own_runtime_errors(self):
        script = '''from frontend import parse_program
from interpreter import Interpreter, LanguageRuntimeError, UndefinedNameError
for source, name in [("missing;", "missing"), ("missing=1;", "missing"),
                     ("missing=other;", "other")]:
    try:
        Interpreter(parse_program(source)).run()
    except UndefinedNameError as error:
        assert isinstance(error, LanguageRuntimeError)
        assert error.name == name
        assert error.pos == source.index(name)
        assert str(error).startswith(str(error.pos + 1) + "文字目:")
    else:
        raise AssertionError(source)
'''
        for stage in ("04", "05", "06", "07"):
            with self.subTest(stage=stage):
                self.execute(stage, script)

    def test_each_stage_run_starts_fresh_and_returns_copies(self):
        script = '''from frontend import parse_program, Program
from interpreter import Interpreter, Result
program = parse_program("let x=2; x=x+3;")
assert isinstance(program, Program)
assert program.functions == {}
runtime = Interpreter(program)
first = runtime.run()
assert isinstance(first, Result)
first.globals["x"] = 99
first.output.append(99)
second = runtime.run()
assert second.output == [] and second.globals == {"x": 5}
assert runtime.globals == {"x": 5} and runtime.output == []
'''
        for stage in ("04", "05", "06", "07"):
            with self.subTest(stage=stage):
                self.execute(stage, script)

    def test_each_stage_is_runnable_with_only_its_own_files(self):
        expected = {
            "04": [[], {"price": 80, "total": 300}],
            "05": [[300], {"price": 80, "total": 300}],
            "06": [[45], {"i": 10, "total": 45}],
            "07": [[720], {}],
        }
        for stage, want in expected.items():
            with self.subTest(stage=stage):
                lines = self.execute(stage).splitlines()
                self.assertEqual([ast.literal_eval(line) for line in lines], want)

    def test_snapshots_preserve_the_original_early_chapter_files(self):
        for stage in ("04", "05", "06", "07"):
            for name in ("chapter01.py", "chapter02.py"):
                with self.subTest(stage=stage, name=name):
                    path = ROOT / "chapters" / stage / name
                    self.assertTrue(path.is_file(), str(path))
                    self.assertEqual(path.read_bytes(), (ROOT / name).read_bytes())

    def test_07_is_the_completed_frontend_and_interpreter(self):
        for name in ("frontend.py", "interpreter.py"):
            with self.subTest(name=name):
                path = ROOT / "chapters" / "07" / name
                self.assertTrue(path.is_file(), str(path))
                self.assertEqual(path.read_bytes(), (ROOT / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
