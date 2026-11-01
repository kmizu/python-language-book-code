from chapter02 import Number, Unary, Binary, parse


def evaluate(node):
    if isinstance(node, Number):
        return node.value

    if isinstance(node, Unary):
        operand = evaluate(node.operand)
        if node.op == "+":
            return +operand
        if node.op == "-":
            return -operand
        raise ValueError(f"未対応の単項演算子です: {node.op}")

    if isinstance(node, Binary):
        left = evaluate(node.left)
        right = evaluate(node.right)
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        raise ValueError(f"未対応の二項演算子です: {node.op}")

    raise TypeError(f"知らないノードです: {type(node).__name__}")


def run(source):
    tree = parse(source)
    return evaluate(tree)


if __name__ == "__main__":
    print(run("100 + 80 * 3"))
