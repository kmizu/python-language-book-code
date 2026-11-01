"""Executable checks for the semantics taught in chapters 1 through 16."""

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from chapter02 import Binary as OriginalBinary
from chapter03 import run as run_expression
from frontend import (Binary, Call, Number, ParseError, lex, parse_program)
from interpreter import (
    ArityError, Interpreter, UndefinedFunctionError, UndefinedNameError,
)
from bytecode import Code, Instruction, compile_program, verify_code, BytecodeError
from vm import VM
from optimizer import optimize_program


class FrontendTests(unittest.TestCase):
    def test_original_expression_classes_and_examples_stay_usable(self):
        self.assertIs(Binary, OriginalBinary)
        self.assertEqual(run_expression("100 + 80 * 3"), 340)

    def test_comments_names_and_positions(self):
        tokens = lex("# note\nlet price_2 = 30;")
        self.assertEqual(
            [(t.kind, t.text, t.pos) for t in tokens[:3]],
            [("LET", "let", 7), ("NAME", "price_2", 11), ("ASSIGN", "=", 19)],
        )

    def test_precedence_and_left_associativity(self):
        result = Interpreter(parse_program("print 10-3-2; print -2*3+8; print 2+3<6;")).run()
        self.assertEqual(result.output, [5, 2, 1])

    def test_chained_comparison_is_rejected(self):
        for source in ["print 1<2<3;", "print 1==1==1;", "print 1<2==1;"]:
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse_program(source)

    def test_command_line_runs_a_source_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "example.mame"
            source.write_text("let price=120; print price*3;", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(CODE_DIR / "run.py"), str(source), "--engine", "vm"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "360")

    def test_malformed_programs_are_rejected(self):
        sources = ["let x=;", "if 1 { print 2;", "print 1", "fn f(x,x) {}",
                   "fn f() {} fn f() {}", "return 1;", "if 1 { fn f() {} }"]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse_program(source)

    def test_decimal_and_invalid_identifier_start_are_rejected(self):
        for source in ["print 1.5;", "let _x=1;", "let あ=1;"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_program(source)


class SemanticTests(unittest.TestCase):
    def engines(self, source):
        program = parse_program(source)
        return [Interpreter(program), VM(compile_program(program)),
                Interpreter(optimize_program(program)),
                VM(compile_program(optimize_program(program)))]

    def check_program(self, source, output, globals_):
        for engine in self.engines(source):
            with self.subTest(engine=type(engine).__name__):
                result = engine.run()
                self.assertEqual(result.output, output)
                self.assertEqual(result.globals, globals_)

    def test_let_rebinds_but_assign_requires_existing_name(self):
        self.check_program("let x=1; let x=2; x=x+3; print x;", [5], {"x": 5})
        for engine in self.engines("x=3;"):
            with self.assertRaises(UndefinedNameError):
                engine.run()

    def test_blocks_share_current_frame(self):
        self.check_program("if 1 { let x=3; } x=x+1; print x;", [4], {"x": 4})

    def test_zero_is_false_and_negative_is_true(self):
        self.check_program("if 0 { print 9; } else { print 2; } if -1 { print 3; }", [2, 3], {})

    def test_all_comparisons_return_integer_zero_or_one(self):
        self.check_program("print 2<3; print 2<=2; print 3>2; print 2>=3; print 2==2; print 2!=2;",
                           [1, 1, 1, 0, 1, 0], {})

    def test_loop_and_empty_loop(self):
        self.check_program("let n=5; let s=0; while n>0 { s=s+n; n=n-1; } while 0 { print 9; } print s;",
                           [15], {"n": 0, "s": 15})

    def test_forward_call_recursion_and_implicit_return(self):
        self.check_program("print fact(6); print empty(); fn fact(n) { if n<=1 { return 1; } return n*fact(n-1); } fn empty() {}",
                           [720, 0], {})

    def test_return_unwinds_nested_blocks_and_loop(self):
        self.check_program("fn f() { while 1 { if 1 { return 8; } print 99; } } print f();", [8], {})

    def test_recursive_frames_keep_independent_locals(self):
        self.check_program("fn f(n) { let saved=n; if n>0 { f(n-1); } return saved; } print f(5); print f(2);",
                           [5, 2], {})

    def test_functions_cannot_read_globals(self):
        for engine in self.engines("let x=7; fn f() { return x; } print f();"):
            with self.assertRaises(UndefinedNameError) as caught:
                engine.run()
            self.assertEqual(caught.exception.name, "x")

    def test_function_local_assignment_does_not_update_global(self):
        self.check_program("let x=7; fn f(x) { x=x+1; return x; } print f(2); print x;", [3, 7], {"x": 7})

    def test_binary_operands_and_arguments_run_left_to_right(self):
        source = "fn mark(x) { print x; return x; } fn sub(a,b) { return a-b; } print mark(10)-mark(3); print sub(mark(8),mark(2));"
        self.check_program(source, [10, 3, 7, 8, 2, 6], {})

    def test_left_operand_failure_prevents_right_side_effect(self):
        for engine in self.engines("fn mark() { print 9; return 1; } print missing+mark();"):
            with self.assertRaises(UndefinedNameError):
                engine.run()
            self.assertEqual(engine.output, [])

    def test_arguments_are_evaluated_before_arity_check(self):
        for engine in self.engines("fn mark() { print 3; return 2; } fn f() {} f(mark());"):
            with self.assertRaises(ArityError):
                engine.run()
            self.assertEqual(engine.output, [3])

    def test_undefined_function_is_distinct_from_variable(self):
        for engine in self.engines("missing();"):
            with self.assertRaises(UndefinedFunctionError):
                engine.run()

    def test_large_integers_keep_exact_meaning(self):
        self.check_program("let x=9223372036854775807; print (x+1)*(x+1);",
                           [85070591730234615865843651857942052864], {"x": 9223372036854775807})

    def test_run_starts_with_fresh_observable_state(self):
        for engine in self.engines("let x=1; print x;"):
            first = engine.run()
            second = engine.run()
            self.assertEqual(first.output, [1])
            self.assertEqual(second.output, [1])
            self.assertIsNot(first.output, second.output)

    def test_call_can_be_used_without_run(self):
        for engine in self.engines("fn f(x) { print x; return x+1; }"):
            self.assertEqual(engine.call("f", [4]), 5)
            self.assertEqual(engine.output, [4])

    def test_small_input_family_against_hand_derived_sum(self):
        for n, want in [(0, 0), (1, 0), (2, 1), (5, 10), (10, 45)]:
            with self.subTest(n=n):
                self.check_program(f"let i=0; let s=0; while i<{n} {{ s=s+i; i=i+1; }} print s;",
                                   [want], {"i": n, "s": want})


class CompilerAndVMTests(unittest.TestCase):
    def test_noncommutative_stack_order(self):
        compiled = compile_program(parse_program("print 10-(3-2);"))
        self.assertEqual(VM(compiled).run().output, [9])

    def test_hook_can_replace_call_without_running_vm(self):
        seen = []
        def hook(name, args, fallback):
            seen.append((name, args))
            return 42
        vm = VM(compile_program(parse_program("fn f() { print 9; return 1; } print f();")), hook=hook)
        self.assertEqual(vm.run().output, [42])
        self.assertEqual(seen, [("f", [])])

    def test_fallback_executes_call_only_once_even_when_invoked_twice(self):
        def hook(name, args, fallback):
            first = fallback()
            self.assertEqual(fallback(), first)
            return first
        vm = VM(compile_program(parse_program("fn f() { print 7; return 8; } print f();")), hook=hook)
        self.assertEqual(vm.run().output, [7, 8])

    def test_fallback_nested_calls_still_use_hook(self):
        seen = []
        def hook(name, args, fallback):
            seen.append(name)
            return fallback()
        vm = VM(compile_program(parse_program("fn f() { return g(); } fn g() { return 6; } print f();")), hook=hook)
        self.assertEqual(vm.run().output, [6])
        self.assertEqual(seen, ["f", "g"])

    def test_hook_cannot_hide_arity_or_unknown_function(self):
        vm = VM(compile_program(parse_program("fn f(x) { return x; }")), hook=lambda n, a, f: 99)
        with self.assertRaises(ArityError):
            vm.call("f", [])
        with self.assertRaises(UndefinedFunctionError):
            vm.call("missing", [])

    def test_fallback_failure_is_not_reexecuted(self):
        def hook(name, args, fallback):
            for _ in range(2):
                with self.assertRaises(UndefinedNameError):
                    fallback()
            return 0
        vm = VM(compile_program(parse_program("fn f() { print 7; return missing; } f();")), hook=hook)
        self.assertEqual(vm.run().output, [7])

    def test_bytecode_return_requires_exactly_one_value(self):
        with self.assertRaises(BytecodeError):
            verify_code(Code("bad", [], [Instruction("PUSH", 1), Instruction("PUSH", 2), Instruction("RETURN")]))

    def test_fallthrough_without_return_is_rejected(self):
        with self.assertRaises(BytecodeError):
            verify_code(Code("bad", [], [Instruction("PUSH", 1), Instruction("POP")]))

    def test_execution_counters_record_both_branch_outcomes(self):
        vm = VM(compile_program(parse_program("let n=2; while n { n=n-1; }")))
        vm.run()
        self.assertGreater(vm.steps, 0)
        self.assertIn({True: 2, False: 1}, vm.branch_counts.values())

    def test_verifier_rejects_underflow_and_bad_target(self):
        for instructions in [[Instruction("ADD"), Instruction("RETURN")],
                             [Instruction("JUMP", 99)],
                             [Instruction("BOGUS")]]:
            with self.subTest(instructions=instructions), self.assertRaises(BytecodeError):
                verify_code(Code("bad", [], instructions))

    def test_verifier_rejects_inconsistent_join_depth(self):
        instructions = [Instruction("PUSH", 1), Instruction("JUMP_FALSE", 4),
                        Instruction("PUSH", 9), Instruction("JUMP", 4),
                        Instruction("PUSH", 0), Instruction("RETURN")]
        with self.assertRaises(BytecodeError):
            verify_code(Code("bad", [], instructions))

    def test_verifier_accepts_compiled_loop_and_calls(self):
        compiled = compile_program(parse_program("fn f(n) { while n { n=n-1; } return n; } print f(3);"))
        verify_code(compiled.main)
        for code in compiled.functions.values():
            verify_code(code)


class OptimizerTests(unittest.TestCase):
    def test_constant_folding_keeps_big_integers_and_positions(self):
        original = parse_program("print (9223372036854775807+1)*2;")
        optimized = optimize_program(original)
        self.assertIsInstance(optimized.body[0].value, Number)
        self.assertEqual(optimized.body[0].value.value, 18446744073709551616)
        self.assertIsInstance(original.body[0].value, Binary)

    def test_zero_multiplication_does_not_erase_name_failure(self):
        for expr in ["0*missing", "missing*0", "missing-missing"]:
            optimized = optimize_program(parse_program("print " + expr + ";"))
            with self.subTest(expr=expr), self.assertRaises(UndefinedNameError):
                Interpreter(optimized).run()

    def test_zero_multiplication_does_not_erase_call_effects(self):
        optimized = optimize_program(parse_program("fn f() { print 7; return 9; } print f()*0; print 0*f();"))
        self.assertEqual(Interpreter(optimized).run().output, [7, 0, 7, 0])

    def test_safe_identities_keep_call_and_name_evaluation(self):
        optimized = optimize_program(parse_program("fn f() { print 3; return 4; } print f()+0; print 1*f();"))
        self.assertIsInstance(optimized.body[0].value, Call)
        self.assertEqual(Interpreter(optimized).run().output, [3, 4, 3, 4])


if __name__ == "__main__":
    unittest.main()
