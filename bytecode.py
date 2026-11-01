"""ASTからスタック命令列へ変換し、命令列を検査する。"""

from collections import deque
from dataclasses import dataclass
from frontend import (Number, Unary, Binary, Name, Call, Let, Assign,
                      Print, Return, If, While, ExprStmt)


@dataclass
class Instruction:
    op: str
    arg: object = None
    pos: int = 0


@dataclass
class Code:
    name: str
    params: list
    instructions: list


@dataclass
class Compiled:
    functions: dict
    main: Code


class BytecodeError(Exception):
    pass


BINARY_OPS = {
    "+": "ADD", "-": "SUB", "*": "MUL", "<": "LT", "<=": "LE",
    ">": "GT", ">=": "GE", "==": "EQ", "!=": "NE",
}


class Compiler:
    def __init__(self):
        self.instructions = []

    def emit(self, op, arg=None, pos=0):
        index = len(self.instructions)
        self.instructions.append(Instruction(op, arg, pos))
        return index

    def patch(self, index, target):
        self.instructions[index].arg = target

    def expr(self, node):
        if isinstance(node, Number):
            self.emit("PUSH", node.value, node.pos)
        elif isinstance(node, Name):
            self.emit("LOAD", node.name, node.pos)
        elif isinstance(node, Unary):
            self.expr(node.operand)
            self.emit({"+": "POS", "-": "NEG"}[node.op], pos=node.pos)
        elif isinstance(node, Binary):
            self.expr(node.left)
            self.expr(node.right)
            self.emit(BINARY_OPS[node.op], pos=node.pos)
        elif isinstance(node, Call):
            for arg in node.args:
                self.expr(arg)
            self.emit("CALL", (node.name, len(node.args)), node.pos)
        else:
            raise TypeError(f"知らない式です: {type(node).__name__}")

    def block(self, body):
        for statement in body:
            self.statement(statement)

    def statement(self, node):
        if isinstance(node, (Let, Assign)):
            self.expr(node.value)
            self.emit("STORE", (node.name, isinstance(node, Assign)), node.pos)
        elif isinstance(node, Print):
            self.expr(node.value)
            self.emit("PRINT", pos=node.pos)
        elif isinstance(node, Return):
            self.expr(node.value)
            self.emit("RETURN", pos=node.pos)
        elif isinstance(node, ExprStmt):
            self.expr(node.value)
            self.emit("POP", pos=node.pos)
        elif isinstance(node, If):
            self.expr(node.condition)
            false_jump = self.emit("JUMP_FALSE", None, node.pos)
            self.block(node.then_body)
            end_jump = self.emit("JUMP", None, node.pos)
            self.patch(false_jump, len(self.instructions))
            self.block(node.else_body)
            self.patch(end_jump, len(self.instructions))
        elif isinstance(node, While):
            start = len(self.instructions)
            self.expr(node.condition)
            end_jump = self.emit("JUMP_FALSE", None, node.pos)
            self.block(node.body)
            self.emit("JUMP", start, node.pos)
            self.patch(end_jump, len(self.instructions))
        else:
            raise TypeError(f"知らない文です: {type(node).__name__}")

    def compile(self, name, params, body):
        self.block(body)
        self.emit("PUSH", 0)
        self.emit("RETURN")
        code = Code(name, list(params), self.instructions)
        verify_code(code)
        return code


def compile_program(program):
    functions = {}
    for name, function in program.functions.items():
        functions[name] = Compiler().compile(name, function.params, function.body)
    main = Compiler().compile("<main>", [], program.body)
    return Compiled(functions, main)


def stack_effect(instruction):
    """必要な入力個数と、実行後に積む個数。"""
    op = instruction.op
    if op in ("PUSH", "LOAD"):
        return 0, 1
    if op in ("STORE", "POP", "PRINT", "JUMP_FALSE", "RETURN"):
        return 1, 0
    if op in ("NEG", "POS"):
        return 1, 1
    if op in BINARY_OPS.values():
        return 2, 1
    if op == "CALL":
        return instruction.arg[1], 1
    if op == "JUMP":
        return 0, 0
    raise BytecodeError(f"未知の命令です: {op}")


def verify_code(code):
    """命令の形式と、到達できる各位置のスタック深さを検査する。

    変数が定義済みか、呼出し先があるかは実行時に確かめる。
    戻り値は各到達位置の深さを格納した辞書。
    """
    instructions = code.instructions
    count = len(instructions)
    if count == 0:
        raise BytecodeError(f"{code.name}: 命令列が空です")
    no_arg = {"POP", "NEG", "POS", "ADD", "SUB", "MUL", "LT", "LE",
              "GT", "GE", "EQ", "NE", "RETURN", "PRINT"}
    for index, instruction in enumerate(instructions):
        op, arg = instruction.op, instruction.arg
        valid = False
        if op == "PUSH":
            valid = type(arg) is int
        elif op == "LOAD":
            valid = isinstance(arg, str)
        elif op == "STORE":
            valid = (isinstance(arg, tuple) and len(arg) == 2
                     and isinstance(arg[0], str) and type(arg[1]) is bool)
        elif op == "CALL":
            valid = (isinstance(arg, tuple) and len(arg) == 2
                     and isinstance(arg[0], str) and type(arg[1]) is int and arg[1] >= 0)
        elif op in ("JUMP", "JUMP_FALSE"):
            valid = type(arg) is int and 0 <= arg < count
        elif op in no_arg:
            valid = arg is None
        if not valid:
            raise BytecodeError(f"{code.name}:{index}: 命令または引数が不正です: {instruction}")

    depths = {0: 0}
    pending = deque([0])
    while pending:
        index = pending.popleft()
        instruction = instructions[index]
        depth = depths[index]
        needed, produced = stack_effect(instruction)
        if depth < needed:
            raise BytecodeError(f"{code.name}:{index}: スタック不足です（{depth}個）")
        after = depth - needed + produced
        if instruction.op == "RETURN":
            if depth != 1:
                raise BytecodeError(f"{code.name}:{index}: RETURNの前には値が1個必要です")
            continue
        if instruction.op == "JUMP":
            successors = [instruction.arg]
        elif instruction.op == "JUMP_FALSE":
            successors = [instruction.arg, index + 1]
        else:
            successors = [index + 1]
        for target in successors:
            if target >= count:
                raise BytecodeError(f"{code.name}:{index}: RETURNなしに命令列の末尾へ進みます")
            if target in depths:
                if depths[target] != after:
                    raise BytecodeError(f"{code.name}:{target}: 合流するスタック深さが一致しません")
            else:
                depths[target] = after
                pending.append(target)
    return depths


def disassemble(code):
    lines = []
    for index, instruction in enumerate(code.instructions):
        argument = "" if instruction.arg is None else " " + repr(instruction.arg)
        lines.append(f"{index:04d} {instruction.op}{argument}")
    return "\n".join(lines)
