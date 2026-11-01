"""Reproduce chapter 22: checked public APIs, warmup and visible checksums.

Run: python benchmark.py
     python benchmark.py --calls 20000 --repeats 5 --warmup 40 --json
     python benchmark.py --vm-only

No expected speed ratio is asserted. Native measurements are omitted when the
backend is unavailable; VM fallback is never relabelled as native execution.
"""
import argparse
import json
import platform
from statistics import median
from time import perf_counter_ns

from frontend import parse_program
from interpreter import Interpreter
from bytecode import compile_program
from vm import VM


def run_benchmark(calls=20000, repeats=5, warmup=40, use_native=True):
    if calls < 1 or repeats < 1 or warmup < 32:
        raise ValueError("calls/repeatsは正、warmupは32以上が必要です")
    program = parse_program(
        "fn price(unit,quantity) { return unit*quantity+3; }"
    )
    interpreter = Interpreter(program)
    vm = VM(compile_program(program))
    operations = [
        ("AST", lambda: interpreter.call("price", [7, 3])),
        ("VM", lambda: vm.call("price", [7, 3])),
    ]
    report = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "calls_per_batch": calls,
        "repeats": repeats,
        "warmup_per_mode": warmup,
        "first_compile_ms": None,
        "measurements": [],
        "omitted": [],
    }
    adaptive = None
    if use_native:
        from native import NativeFunction, NativeUnavailable, UnsupportedNative
        from adaptive import AdaptiveRuntime
        try:
            started = perf_counter_ns()
            native = NativeFunction(program.functions["price"])
            report["first_compile_ms"] = (perf_counter_ns() - started) / 1e6
        except (NativeUnavailable, UnsupportedNative) as error:
            report["omitted"].append("native/adaptive: " + str(error))
        else:
            import llvmlite
            from llvmlite import binding as llvm
            report["environment"]["llvmlite"] = llvmlite.__version__
            report["environment"]["llvm"] = list(llvm.llvm_version_info)

            def native_operation():
                ok, value = native.try_call([7, 3])
                if not ok:
                    raise RuntimeError("native計測が適用不可になりました")
                return value

            adaptive = AdaptiveRuntime(program, threshold=8, profile_threshold=32)
            operations.extend([
                ("Native.try_call", native_operation),
                ("Adaptive warm", lambda: adaptive.vm.call("price", [7, 3])),
            ])
    else:
        report["omitted"].append("native/adaptive: --vm-onlyで省略")

    expected = 24 * calls
    for name, operation in operations:
        for _ in range(warmup):
            if operation() != 24:
                raise AssertionError("warmupで計算結果が一致しません")
        if name == "Adaptive warm":
            if (adaptive.native_hits == 0 or "price" not in adaptive.specialized):
                report["omitted"].append("adaptive: nativeの準備を確認できず省略")
                continue
            before_fallbacks = adaptive.fallbacks
        batches = []
        for _ in range(repeats):
            started = perf_counter_ns()
            checksum = sum(operation() for _ in range(calls))
            elapsed_ms = (perf_counter_ns() - started) / 1e6
            if checksum != expected:
                raise AssertionError(f"{name}: checksumが一致しません")
            batches.append(elapsed_ms)
        if name == "Adaptive warm" and adaptive.fallbacks != before_fallbacks:
            raise RuntimeError("native計測中にVM fallbackが混ざりました")
        report["measurements"].append({
            "name": name,
            "batch_ms": batches,
            "median_ms": median(batches),
            "checksum": checksum,
        })
    if adaptive is not None:
        report["adaptive_counters"] = {
            "calls": dict(adaptive.calls),
            "compilations": adaptive.compilations,
            "native_hits": adaptive.native_hits,
            "guard_misses": adaptive.guard_misses,
            "fallbacks": adaptive.fallbacks,
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=int, default=20000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=40)
    parser.add_argument("--vm-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run_benchmark(args.calls, args.repeats, args.warmup, not args.vm_only)
    except ValueError as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    for key, value in report["environment"].items():
        print(f"{key}: {value}")
    print(f"warmup={args.warmup}, calls/batch={args.calls}, repeats={args.repeats}")
    if report["first_compile_ms"] is not None:
        print(f"first NativeFunction construction: {report['first_compile_ms']:.3f} ms")
    for row in report["measurements"]:
        print(f"{row['name']}: median={row['median_ms']:.3f} ms, "
              f"checksum={row['checksum']}")
        print("  batches:", ", ".join(f"{x:.3f}" for x in row["batch_ms"]))
    for note in report["omitted"]:
        print("omitted:", note)
    if "adaptive_counters" in report:
        print("adaptive:", report["adaptive_counters"])


if __name__ == "__main__":
    main()
