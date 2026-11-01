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

## 章ごとのコードで進める

第4～7章には、その章までの機能だけを持つコードを`chapters/`に用意しています。各フォルダーは単独で動き、`chapter01.py`・`chapter02.py`・`frontend.py`・`interpreter.py`・`run.py`を収めています。

| フォルダー | この章までに使える機能 |
| --- | --- |
| `chapters/04/` | 整数の式、名前、`let`、代入、`;`、`#`コメント、式文 |
| `chapters/05/` | 第4章の機能に`print`と`if`・`else`を追加。条件は0を偽、非0を真とする |
| `chapters/06/` | 第5章の機能に比較6種と`while`を追加。比較の連鎖は拒否する |
| `chapters/07/` | 関数定義・呼出し・`return`・再帰を含む、完成版の構文解析とインタプリタ |

リポジトリのルートから、各章の小さな例を実行できます。出力の1行目は`Result.output`、2行目は`Result.globals`です。

```console
python chapters/04/run.py
python chapters/05/run.py
python chapters/06/run.py
python chapters/07/run.py
```

自分で書き足すときは、その章のフォルダーを作業場所にします。たとえば第4章では、次のように実行します。

```console
cd chapters/04
python run.py
```

`frontend.py`の`parse_program`でプログラム全体を読み、`Interpreter(program).run()`で実行します。第4章の`print`や第5章の比較など、まだ導入していない構文は受け付けません。第7章の`frontend.py`と`interpreter.py`は、ルートの完成版と同じ内容です。

## JITを使う

JITには、Python 3.10または3.12と`llvmlite`を使います。ここではPython 3.10を指定して仮想環境を作り、その環境のPythonでインストールと実行を行います。すべてリポジトリのルートで実行してください。

WindowsのPowerShellでは、次のコマンドを使います。

```powershell
py -3.10 --version
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-jit.txt
.\.venv\Scripts\python.exe run.py examples/native.mame --engine adaptive
```

Linux・macOSでは、次のコマンドを使います。

```sh
python3.10 --version
python3.10 -m venv .venv
.venv/bin/python -m pip install -r requirements-jit.txt
.venv/bin/python run.py examples/native.mame --engine adaptive
```

Python 3.10がない場合は、`py -3.10`を`py -3.12`、`python3.10`を`python3.12`に置き換え、Python 3.12で同じ手順を進めてください。仮想環境を作った後のコマンドは同じです。仮想環境のPythonを直接指定するので、Activateコマンドを実行する必要はありません。

`native.mame`は`1960`を出力します。依存ライブラリは`llvmlite==0.43.0`に固定しています。書籍で測定した環境は、Python 3.10.11、llvmlite 0.43.0、LLVM 14.0.6、Windows x86_64です。

JITの対象は、純粋な整数の`return`式一つを持つ関数です。整数リテラルと引数、単項の`+`・`-`、加算・減算・乗算、比較に対応します。関数呼出し、代入、出力、ループなどを含む関数はVMで実行します。

入力とすべての中間値をPythonで計算して、符号付き64ビット整数に収まることを確認してから機械語を実行します。範囲外の値や対応外の処理はVMに戻すので、まめ言語の任意精度整数の意味を保てます。関数入口のガードと実行方法の切り替えを実装しており、関数途中の状態を復元する脱最適化やOSRは含みません。

この事前検査と実行方法の管理にも時間がかかります。JITによる高速化を保証する実装ではありません。

## テストと測定

```console
python -m unittest discover -s tests -v
python benchmark.py --vm-only
```

JITを含むテストと測定には、「JITを使う」で準備した仮想環境のPythonを使います。

WindowsのPowerShellでは、次のコマンドを実行します。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe benchmark.py
```

Linux・macOSでは、次のコマンドを使います。

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python benchmark.py
```

`llvmlite`がない環境では、JITを必要とするテストはスキップされます。GitHub Actionsでは、Windows・LinuxとPython 3.10・3.12の4通りで、依存ライブラリをインストールしてテストを実行します。

## 書籍との対応

本書に対応する版は、`book-v1.0.0`タグとして公開する予定です。[対応版のZIP（公開予定）](https://github.com/kmizu/python-language-book-code/archive/refs/tags/book-v1.0.0.zip)は、タグの作成後にダウンロードできます。

`main`は更新されることがあります。書籍のコードと照合するときは、タグまたはコミットIDで使用する版を固定してください。
