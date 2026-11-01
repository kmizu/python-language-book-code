"""この章で使える構文だけを使った、小さな実行例。"""
from frontend import parse_program
from interpreter import Interpreter


source = 'let i=0; let total=0; while i<10 { total=total+i; i=i+1; } print total;'
result = Interpreter(parse_program(source)).run()
print(result.output)
print(result.globals)
