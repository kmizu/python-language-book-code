"""値と評価の有無を保つ、控えめなAST最適化。"""

from frontend import (Number, Unary, Binary, Name, Call, Let, Assign,
                      Print, Return, If, While, ExprStmt, Function, Program)
from interpreter import apply_binary, apply_unary


def is_number(node, value):
    return isinstance(node, Number) and node.value == value


def optimize_expr(node):
    if isinstance(node, Number):
        return Number(node.value, node.pos)
    if isinstance(node, Name):
        return Name(node.name, node.pos)
    if isinstance(node, Call):
        return Call(node.name, [optimize_expr(arg) for arg in node.args], node.pos)
    if isinstance(node, Unary):
        operand = optimize_expr(node.operand)
        if isinstance(operand, Number):
            return Number(apply_unary(node.op, operand.value), node.pos)
        return Unary(node.op, operand, node.pos)
    if isinstance(node, Binary):
        left = optimize_expr(node.left)
        right = optimize_expr(node.right)
        if isinstance(left, Number) and isinstance(right, Number):
            return Number(apply_binary(node.op, left.value, right.value), node.pos)
        # 取り除くのは数リテラルだけ。NameやCallの評価を消さない。
        if node.op == "+":
            if is_number(right, 0):
                return left
            if is_number(left, 0):
                return right
        if node.op == "-" and is_number(right, 0):
            return left
        if node.op == "*":
            if is_number(right, 1):
                return left
            if is_number(left, 1):
                return right
        return Binary(node.op, left, right, node.pos)
    raise TypeError(f"知らない式です: {type(node).__name__}")


def optimize_statement(node):
    if isinstance(node, Let):
        return Let(node.name, optimize_expr(node.value), node.pos)
    if isinstance(node, Assign):
        return Assign(node.name, optimize_expr(node.value), node.pos)
    if isinstance(node, Print):
        return Print(optimize_expr(node.value), node.pos)
    if isinstance(node, Return):
        return Return(optimize_expr(node.value), node.pos)
    if isinstance(node, ExprStmt):
        return ExprStmt(optimize_expr(node.value), node.pos)
    if isinstance(node, If):
        return If(optimize_expr(node.condition), optimize_block(node.then_body),
                  optimize_block(node.else_body), node.pos)
    if isinstance(node, While):
        return While(optimize_expr(node.condition), optimize_block(node.body), node.pos)
    raise TypeError(f"知らない文です: {type(node).__name__}")


def optimize_block(body):
    return [optimize_statement(node) for node in body]


def optimize_program(program):
    functions = {}
    for name, function in program.functions.items():
        functions[name] = Function(name, list(function.params), optimize_block(function.body), function.pos)
    return Program(functions, optimize_block(program.body))
