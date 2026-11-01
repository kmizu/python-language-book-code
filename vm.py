"""フレームごとのスタックと変数を持つ、まめ言語のVM。"""

from dataclasses import dataclass, field
from bytecode import verify_code
from interpreter import (Result, UndefinedNameError, UndefinedFunctionError,
                         ArityError, apply_binary, apply_unary)


@dataclass
class Frame:
    code: object
    env: dict
    stack: list = field(default_factory=list)
    ip: int = 0


BINARY_SYMBOLS = {"ADD": "+", "SUB": "-", "MUL": "*", "LT": "<", "LE": "<=",
                  "GT": ">", "GE": ">=", "EQ": "==", "NE": "!="}


class VM:
    def __init__(self, compiled, hook=None):
        self.compiled = compiled
        self.hook = hook
        self.output = []
        self.globals = {}
        self.steps = 0
        self.branch_counts = {}
        self.frames = []
        verify_code(compiled.main)
        for code in compiled.functions.values():
            verify_code(code)

    def run(self):
        self.output = []
        self.globals = {}
        self.steps = 0
        self.branch_counts = {}
        self._execute(self.compiled.main, self.globals)
        return Result(list(self.output), dict(self.globals))

    def call(self, name, args, pos=0):
        if name not in self.compiled.functions:
            raise UndefinedFunctionError(name, pos)
        code = self.compiled.functions[name]
        if len(args) != len(code.params):
            raise ArityError(name, len(code.params), len(args), pos)
        # 値を写し、hookが受け取るリストから通常実行の引数を切り離す。
        arguments = list(args)
        done = False
        value = None
        failure = None

        def fallback():
            nonlocal done, value, failure
            if not done:
                # 例外を含め、同じ呼出しの副作用を繰り返さない。
                done = True
                try:
                    local = dict(zip(code.params, arguments))
                    value = self._execute(code, local)
                except Exception as error:
                    failure = error
            if failure is not None:
                raise failure
            return value

        if self.hook is None:
            return fallback()
        return self.hook(name, list(arguments), fallback)

    def _execute(self, code, env):
        frame = Frame(code, env)
        self.frames.append(frame)
        try:
            while True:
                index = frame.ip
                instruction = code.instructions[index]
                frame.ip += 1
                self.steps += 1
                op, arg, pos = instruction.op, instruction.arg, instruction.pos
                stack = frame.stack
                if op == "PUSH":
                    stack.append(arg)
                elif op == "LOAD":
                    if arg not in env:
                        raise UndefinedNameError(arg, pos)
                    stack.append(env[arg])
                elif op == "STORE":
                    value = stack.pop()
                    name, require_existing = arg
                    if require_existing and name not in env:
                        raise UndefinedNameError(name, pos)
                    env[name] = value
                elif op == "POP":
                    stack.pop()
                elif op in ("NEG", "POS"):
                    symbol = "-" if op == "NEG" else "+"
                    stack.append(apply_unary(symbol, stack.pop()))
                elif op in BINARY_SYMBOLS:
                    right = stack.pop()
                    left = stack.pop()
                    stack.append(apply_binary(BINARY_SYMBOLS[op], left, right))
                elif op == "JUMP":
                    frame.ip = arg
                elif op == "JUMP_FALSE":
                    condition = stack.pop() != 0
                    counts = self.branch_counts.setdefault((code.name, index), {True: 0, False: 0})
                    counts[condition] += 1
                    if not condition:
                        frame.ip = arg
                elif op == "CALL":
                    name, argc = arg
                    # popを繰り返すと逆順になる。末尾の並びをそのまま渡す。
                    arguments = stack[-argc:] if argc else []
                    if argc:
                        del stack[-argc:]
                    stack.append(self.call(name, arguments, pos))
                elif op == "PRINT":
                    self.output.append(stack.pop())
                elif op == "RETURN":
                    return stack.pop()
                else:
                    # VM構築時の検証があるので、通常ここへは来ない。
                    raise ValueError(f"未知の命令です: {op}")
        finally:
            self.frames.pop()
