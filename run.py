"""実行例: python run.py examples/receipt.mame --engine vm"""

import argparse
from pathlib import Path
from frontend import parse_program
from interpreter import Interpreter
from bytecode import compile_program, disassemble
from vm import VM
from optimizer import optimize_program


def main():
    parser = argparse.ArgumentParser(description="まめ言語のソースを実行します")
    parser.add_argument("source", type=Path)
    parser.add_argument("--engine", choices=["interpreter", "vm", "adaptive"], default="vm")
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--dump", action="store_true", help="命令列も表示します")
    args = parser.parse_args()
    program = parse_program(args.source.read_text(encoding="utf-8"))
    if args.optimize:
        program = optimize_program(program)
    if args.dump:
        compiled = compile_program(program)
        for code in [compiled.main, *compiled.functions.values()]:
            print(f"== {code.name} ==")
            print(disassemble(code))
    if args.engine == "interpreter":
        runtime = Interpreter(program)
    elif args.engine == "vm":
        runtime = VM(compile_program(program))
    else:
        from adaptive import AdaptiveRuntime
        runtime = AdaptiveRuntime(program)
    result = runtime.run()
    for value in result.output:
        print(value)


if __name__ == "__main__":
    main()
