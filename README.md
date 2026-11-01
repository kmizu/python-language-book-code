# 『Pythonでつくるプログラミング言語』サンプルコード

Pythonで小さな「まめ言語」を作る、書籍『Pythonでつくるプログラミング言語』のサンプルコードです。字句解析・構文解析から始め、構文木をたどるインタプリタ、スタックVM、最適化、LLVMによるJIT、呼出し回数と引数の記録に基づく実行方法の切り替えまでを扱います。

Pythonの基礎を知っている読者を想定しています。コード、実行例、テスト、測定用プログラムを収めています。

## まず動かす

Python 3.10以降を使います。通常のインタプリタ・VM・最適化は、Pythonの標準ライブラリだけで動きます。

```console
git clone https://github.com/kmizu/python-language-book-code.git
cd python-language-book-code
python chapter01.py
python chapter02.py
python chapter03.py
python run.py examples/receipt.mame --engine interpreter
python run.py examples/receipt.mame --engine vm
```

以降のコマンドも、すべてリポジトリのルートで実行します。`receipt.mame`の出力は`460`です。第1～3章のファイルはそれぞれ独立しており、第4章以降の完成版は`frontend.py`から始まります。

```console
python run.py examples/factorial.mame --engine vm
python run.py examples/order.mame --engine vm
python run.py examples/sum.mame --engine vm --dump
python run.py examples/sum.mame --engine vm --optimize
```

`factorial.mame`は`720`、`sum.mame`は`45`を出力します。`order.mame`は`10`、`3`、`7`、`8`、`2`、`6`を一行ずつ出力します。`--dump`を付けるとVMの命令列も表示します。

## ファイルの構成

| ファイル | 内容 |
| --- | --- |
| `chapter01.py`～`chapter03.py` | 最初の3章で作る計算機 |
| `frontend.py` | トークン化、構文解析、構文木 |
| `interpreter.py` | 構文木をたどるインタプリタ |
| `bytecode.py` | VMの命令への変換、逆アセンブル、命令列の検査 |
| `vm.py` | スタックVM |
| `optimizer.py` | 構文木の定数計算と式の簡約 |
| `native.py` | LLVMによる機械語の生成と整数の範囲検査 |
| `adaptive.py` | 呼出し回数と引数の記録、JITとVMの切り替え |
| `run.py`、`mame.py` | コマンドラインからの実行 |
| `benchmark.py` | 第22章の測定用プログラム |
| `examples/` | まめ言語の実行例 |
| `tests/` | 通常実行、エラー、JIT、CLIなどのテスト |

## JITを使う

JITには`llvmlite`が必要です。仮想環境を作成してから、依存ライブラリをインストールします。

```console
python -m venv .venv
```

WindowsのPowerShellでは、次のコマンドで仮想環境を有効にします。

```powershell
.venv\Scripts\Activate.ps1
```

Linux・macOSでは、次のコマンドを使います。

```sh
source .venv/bin/activate
```

```console
python -m pip install -r requirements-jit.txt
python run.py examples/native.mame --engine adaptive
```

`native.mame`は`1960`を出力します。依存ライブラリは`llvmlite==0.43.0`に固定しています。書籍で測定した環境は、Python 3.10.11、llvmlite 0.43.0、LLVM 14.0.6、Windows x86_64です。

JITの対象は、純粋な整数の`return`式一つを持つ関数です。整数リテラルと引数、単項の`+`・`-`、加算・減算・乗算、比較に対応します。関数呼出し、代入、出力、ループなどを含む関数はVMで実行します。

入力とすべての中間値をPythonで計算して、符号付き64ビット整数に収まることを確認してから機械語を実行します。範囲外の値や対応外の処理はVMに戻すので、まめ言語の任意精度整数の意味を保てます。関数入口のガードと実行方法の切り替えを実装しており、関数途中の状態を復元する脱最適化やOSRは含みません。

この事前検査と実行方法の管理にも時間がかかります。JITによる高速化を保証する実装ではありません。

## テストと測定

```console
python -m unittest discover -s tests -v
python benchmark.py --vm-only
```

JITを含むテストと測定は、`requirements-jit.txt`をインストールしてから実行します。

```console
python -m unittest discover -s tests -v
python benchmark.py
```

`llvmlite`がない環境では、JITを必要とするテストはスキップされます。GitHub Actionsでは、Windows・LinuxとPython 3.10・3.12の4通りで、依存ライブラリをインストールしてテストを実行します。

## 書籍との対応

`main`は更新されることがあります。書籍のコードと照合するときは、タグまたはコミットIDで使用する版を固定してください。
