"""この章で使える構文だけを使った、小さな実行例。"""
from frontend import parse_program
from interpreter import Interpreter


source = 'fn factorial(n) { if n<=1 { return 1; } return n*factorial(n-1); } print factorial(6);'
result = Interpreter(parse_program(source)).run()
print(result.output)
print(result.globals)
