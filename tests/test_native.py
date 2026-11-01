"""Native code, range fallback and the adaptive entry policy."""
from pathlib import Path
import gc
import importlib.util
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from native import NativeFunction, UnsupportedNative
from adaptive import AdaptiveRuntime
from frontend import parse_program


HAS_LLVM = importlib.util.find_spec("llvmlite") is not None


def function(source, name="f"):
    return parse_program(source).functions[name]


@unittest.skipUnless(HAS_LLVM, "llvmlite is an optional backend")
class NativeTests(unittest.TestCase):
    def test_machine_code_computes_signed_arithmetic(self):
        native = NativeFunction(function("fn f(x,y) { return -(x-y)*+y+3; }"))
        self.assertEqual(native.try_call([10, 4]), (True, -21))
        self.assertEqual(native.try_call([-2, 3]), (True, 18))
        self.assertGreater(native.address, 0)
        self.assertEqual(native.native_calls, 2)

    def test_comparisons_return_integer_zero_or_one(self):
        cases = [("<", 1), ("<=", 1), (">", 0), (">=", 0),
                 ("==", 0), ("!=", 1)]
        for op, want in cases:
            with self.subTest(op=op):
                native = NativeFunction(function(f"fn f(x,y) {{ return x {op} y; }}"))
                self.assertEqual(native.try_call([-4, 2]), (True, want))
                self.assertIs(type(native.try_call([2, 2])[1]), int)

    def test_no_parameters_and_nested_comparison(self):
        native = NativeFunction(function("fn f() { return (2<3)+4*5; }"))
        self.assertEqual(native.try_call([]), (True, 21))

    def test_signed_boundaries_are_not_truncated(self):
        native = NativeFunction(function("fn f(x) { return x; }"))
        self.assertEqual(native.try_call([-(1 << 63)]), (True, -(1 << 63)))
        self.assertEqual(native.try_call([(1 << 63)-1]), (True, (1 << 63)-1))
        self.assertEqual(native.try_call([1 << 63]), (False, None))
        self.assertEqual(native.try_call([-(1 << 63)-1]), (False, None))
        self.assertEqual(native.native_calls, 2)

    def test_overflowing_intermediate_falls_back_even_when_result_fits(self):
        native = NativeFunction(function("fn f(x) { return (x+1)-1; }"))
        self.assertEqual(native.try_call([(1 << 63)-1]), (False, None))
        self.assertEqual(native.native_calls, 0)

    def test_subtract_multiply_and_negation_overflow(self):
        cases = [("x-1", -(1 << 63)), ("x*2", (1 << 62)),
                 ("-x", -(1 << 63))]
        for expr, value in cases:
            with self.subTest(expr=expr):
                native = NativeFunction(function(f"fn f(x) {{ return {expr}; }}"))
                self.assertEqual(native.try_call([value]), (False, None))

    def test_big_literal_does_not_wrap_during_code_generation(self):
        native = NativeFunction(function("fn f() { return 9223372036854775808; }"))
        self.assertEqual(native.try_call([]), (False, None))
        self.assertEqual(native.native_calls, 0)

    def test_entry_rejects_wrong_arity_non_integer_and_unused_big_argument(self):
        native = NativeFunction(function("fn f(x,y) { return x; }"))
        for args in [[1], [1, 2, 3], [1.5, 2], [True, 2], [1, 1 << 80]]:
            with self.subTest(args=args):
                self.assertEqual(native.try_call(args), (False, None))

    def test_constant_version_is_guarded_even_when_called_directly(self):
        native = NativeFunction(function("fn f(x,y) { return x*y+1; }"), {"x": 7})
        self.assertEqual(native.try_call([7, 3]), (True, 22))
        self.assertEqual(native.try_call([8, 3]), (False, None))

    def test_engine_survives_collection(self):
        native = NativeFunction(function("fn f(x) { return x*3; }"))
        gc.collect()
        self.assertEqual(native.try_call([14]), (True, 42))

    def test_side_effect_call_and_unknown_variable_are_not_native(self):
        sources = ["fn f(x) { print x; return x; }",
                   "fn f(x) { let y=x; return y; }",
                   "fn f(x) { return f(x); }",
                   "fn f(x) { return y; }"]
        for source in sources:
            with self.subTest(source=source):
                with self.assertRaises(UnsupportedNative):
                    NativeFunction(function(source))


@unittest.skipUnless(HAS_LLVM, "llvmlite is an optional backend")
class AdaptiveTests(unittest.TestCase):
    def test_vm_runs_before_threshold_and_native_after(self):
        runtime = AdaptiveRuntime(parse_program("fn f(x) { return x*2+1; }"),
                                  threshold=3, profile_threshold=99)
        self.assertEqual([runtime.vm.call("f", [x]) for x in [1, 2, 3, 4]],
                         [3, 5, 7, 9])
        self.assertEqual(runtime.calls["f"], 4)
        self.assertEqual(runtime.compilations, 1)
        self.assertEqual(runtime.native_hits, 2)
        self.assertEqual(runtime.fallbacks, 2)

    def test_profile_specializes_at_eighty_percent_and_guard_miss_uses_general(self):
        runtime = AdaptiveRuntime(parse_program("fn f(x,y) { return x*y+1; }"),
                                  threshold=2, profile_threshold=5)
        for x in [7, 7, 7, 8, 7]:
            self.assertEqual(runtime.vm.call("f", [x, 3]), x*3+1)
        self.assertEqual(runtime.compilations, 2)
        self.assertEqual(runtime.specialized["f"].constants, {"x": 7})
        hits = runtime.native_hits
        self.assertEqual(runtime.vm.call("f", [9, 3]), 28)
        self.assertEqual(runtime.guard_misses, 1)
        self.assertEqual(runtime.native_hits, hits+1)

    def test_profile_does_not_specialize_below_eighty_percent(self):
        runtime = AdaptiveRuntime(parse_program("fn f(x) { return x+1; }"),
                                  threshold=1, profile_threshold=5)
        for x in [1, 2, 1, 2, 1]:
            runtime.vm.call("f", [x])
        self.assertEqual(runtime.compilations, 1)
        self.assertNotIn("f", runtime.specialized)

    def test_dominant_value_can_change_without_wrong_results(self):
        runtime = AdaptiveRuntime(parse_program("fn f(x) { return x+1; }"),
                                  threshold=2, profile_threshold=4)
        for x in [7]*4 + [9]*20:
            self.assertEqual(runtime.vm.call("f", [x]), x+1)
        self.assertEqual(runtime.specialized["f"].constants, {"x": 9})
        self.assertEqual(runtime.compilations, 3)
        self.assertGreater(runtime.guard_misses, 0)

    def test_large_intermediate_keeps_arbitrary_precision(self):
        runtime = AdaptiveRuntime(parse_program("fn f(x) { return (x+1)-1; }"),
                                  threshold=1, profile_threshold=99)
        value = (1 << 63)-1
        self.assertEqual(runtime.vm.call("f", [value]), value)
        self.assertEqual(runtime.native_hits, 0)
        self.assertEqual(runtime.fallbacks, 1)

    def test_side_effect_function_uses_vm_once_per_call(self):
        program = parse_program("fn f(x) { print x; return x+1; } print f(7); print f(8);")
        runtime = AdaptiveRuntime(program, threshold=1, profile_threshold=2)
        result = runtime.run()
        self.assertEqual(result.output, [7, 8, 8, 9])
        self.assertEqual(runtime.compilations, 0)
        self.assertEqual(runtime.fallbacks, 2)

    def test_fallback_call_still_profiles_nested_pure_function(self):
        program = parse_program("fn inner(x) { return x+2; } "
                                "fn outer(x) { return inner(x)*3; } "
                                "print outer(4); print outer(5);")
        runtime = AdaptiveRuntime(program, threshold=1, profile_threshold=99)
        self.assertEqual(runtime.run().output, [18, 21])
        self.assertEqual(dict(runtime.calls), {"outer": 2, "inner": 2})
        self.assertEqual(runtime.compilations, 1)
        self.assertEqual(runtime.native_hits, 2)


class BenchmarkTests(unittest.TestCase):
    def test_vm_only_report_has_correct_checksum_and_no_native_measurement(self):
        from benchmark import run_benchmark
        report = run_benchmark(calls=10, repeats=2, warmup=32, use_native=False)
        self.assertEqual([row["name"] for row in report["measurements"]],
                         ["AST", "VM"])
        self.assertIsNone(report["first_compile_ms"])
        for row in report["measurements"]:
            self.assertEqual(row["checksum"], 240)
            self.assertEqual(len(row["batch_ms"]), 2)

    @unittest.skipUnless(HAS_LLVM, "llvmlite is an optional backend")
    def test_native_report_measures_real_native_calls(self):
        from benchmark import run_benchmark
        report = run_benchmark(calls=10, repeats=2, warmup=32)
        self.assertEqual([row["name"] for row in report["measurements"]],
                         ["AST", "VM", "Native.try_call", "Adaptive warm"])
        self.assertGreater(report["adaptive_counters"]["native_hits"], 20)
        self.assertEqual(report["adaptive_counters"]["compilations"], 2)
        self.assertEqual(report["adaptive_counters"]["fallbacks"], 7)
        for row in report["measurements"]:
            self.assertEqual(row["checksum"], 240)


class BackendAvailabilityTests(unittest.TestCase):
    def test_backend_import_failure_keeps_the_adaptive_vm_available(self):
        code_dir = Path(__file__).resolve().parents[1]
        for error_type in ["ImportError", "OSError"]:
            with self.subTest(error_type=error_type):
                script = '''
import builtins
original_import = builtins.__import__
def missing_backend(name, *args, **kwargs):
    if name == "llvmlite":
        raise ERROR_TYPE("backend load unavailable")
    return original_import(name, *args, **kwargs)
builtins.__import__ = missing_backend
from frontend import parse_program
from adaptive import AdaptiveRuntime
program = parse_program("fn f(x) { return x+1; } print f(23);")
runtime = AdaptiveRuntime(program, threshold=1)
assert runtime.run().output == [24]
assert runtime.compilations == 0
assert runtime.native_hits == 0
assert runtime.fallbacks == 1
assert "ERROR_NAME" in runtime.unavailable["f"]
print("VM fallback preserved")
'''.replace("ERROR_TYPE", error_type).replace("ERROR_NAME", error_type)
                completed = subprocess.run([sys.executable, "-c", script],
                                           cwd=code_dir, capture_output=True,
                                           text=True, encoding="utf-8", errors="replace")
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout.strip(), "VM fallback preserved")


if __name__ == "__main__":
    unittest.main()
