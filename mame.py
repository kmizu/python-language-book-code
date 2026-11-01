"""まめ言語のファイルを実行する、小さなコマンドラインツール。"""
import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='まめ言語を実行します')
    parser.add_argument('path', type=Path, help='UTF-8のソースファイル')
    parser.add_argument('--engine', choices=['tree', 'vm', 'adaptive'], default='vm')
    arguments = parser.parse_args(argv)
    try:
        source = arguments.path.read_text(encoding='utf-8')
        from frontend import parse_program
        program = parse_program(source)
        if arguments.engine == 'tree':
            from interpreter import Interpreter
            result = Interpreter(program).run()
        elif arguments.engine == 'vm':
            from bytecode import compile_program
            from vm import VM
            result = VM(compile_program(program)).run()
        else:
            from adaptive import AdaptiveRuntime
            result = AdaptiveRuntime(program).run()
    except (OSError, UnicodeError) as error:
        print(f'{arguments.path}: ファイルを読めません: {error}', file=sys.stderr)
        return 1
    except Exception as error:
        # 学習用ツールでは例外名も残し、本文のエラーと照合できるようにする。
        print(f'{arguments.path}: {type(error).__name__}: {error}', file=sys.stderr)
        return 1
    for value in result.output:
        print(value)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
