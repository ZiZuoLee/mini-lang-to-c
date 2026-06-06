# mini-lang-to-c

复旦大学《程序设计语言原理》Final Project。

本项目实现一个小型语言到 C 语言的处理程序。输入文件是 `sample.mini`，处理程序 `transpiler.py` 会把其中的语言特征翻译成可编译运行的 C 文件 `output.c`。

## 文件说明

- `sample.mini`：示例输入文件，包含功能说明注释和期望输出。
- `transpiler.py`：处理程序，使用 Python 实现词法/语法范围内的简单转译。
- `output.c`：由处理程序生成的 C 代码文件。

## 已支持功能

1. Rust 风格 `Option<int>`：`Some(value)`、`None`。
2. `is_some(option)` 与 `is_none(option)` 判断。
3. `match option { Some(x) => ..., None => ... }`。
4. 数组字面量传入 `find([..], target)`，返回 `Some(value)` 或 `None`。
5. 函数赋值给变量：`let double = fn(x) { x * 2 }`。
6. 简单闭包：`let add = fn(a) { fn(b) { a + b } }`。
7. Lambda 写法：`let triple = fn x => x * 3`。

## 运行方法

生成 C 文件：

```bash
python transpiler.py sample.mini -o output.c
```

编译 C 文件：

```bash
gcc output.c -o output
```

运行：

```bash
./output
```

期望输出：

```text
true
true
11
Some(5)
None
20
7
21
```

- `Option` 被翻译为带有 `is_some` 标记和 `value` 字段的结构体。
- `match` 被翻译为 C 条件表达式。
- 函数值被翻译为 C 函数。
- 简单闭包被翻译为保存外层变量的结构体加 apply 函数。
