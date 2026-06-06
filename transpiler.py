#!/usr/bin/env python3
"""
Mini language to C transpiler.

The goal is intentionally small: translate the course sample language features
into plain C code that can be compiled with a normal C compiler.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


class TranspileError(Exception):
    pass


class Transpiler:
    def __init__(self, source: str) -> None:
        self.source = source
        self.lines = self._code_lines(source)
        self.out: list[str] = []
        self.var_types: dict[str, str] = {}
        self.functions: dict[str, str] = {}
        self.c_names: dict[str, str] = {}
        self.array_id = 0

    def _code_lines(self, source: str) -> list[str]:
        lines: list[str] = []
        for raw in source.splitlines():
            code = raw.split("//", 1)[0].rstrip()
            if code.strip():
                lines.append(code)
        return lines

    def transpile(self) -> str:
        i = 0
        while i < len(self.lines):
            line = self.lines[i].strip()

            if self._is_named_function(line):
                block, i = self._collect_block(i)
                self._emit_named_function(block)
                continue

            if line.startswith("let ") and " match " in line:
                block, i = self._collect_match(i)
                self._emit_match_assignment(block)
                continue

            if line.startswith("let ") and "= fn" in line:
                block, i = self._collect_fn_assignment(i)
                self._emit_fn_assignment(block)
                continue

            if line.startswith("let "):
                self._emit_let(line)
                i += 1
                continue

            self._emit_expression_statement(line)
            i += 1

        return self._render_c()

    def _is_named_function(self, line: str) -> bool:
        return bool(re.match(r"^[A-Za-z_]\w*\s*\([^)]*\)\s*\{$", line))

    def _collect_block(self, start: int) -> tuple[list[str], int]:
        block: list[str] = []
        depth = 0
        i = start
        while i < len(self.lines):
            line = self.lines[i]
            block.append(line)
            depth += line.count("{") - line.count("}")
            i += 1
            if depth == 0:
                break
        if depth != 0:
            raise TranspileError(f"unclosed block near: {self.lines[start]}")
        return block, i

    def _collect_match(self, start: int) -> tuple[list[str], int]:
        return self._collect_block(start)

    def _collect_fn_assignment(self, start: int) -> tuple[list[str], int]:
        line = self.lines[start].strip()
        if "=>" in line:
            return [line], start + 1
        return self._collect_block(start)

    def _emit_named_function(self, block: list[str]) -> None:
        header = block[0].strip()
        match = re.match(r"^([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{$", header)
        if not match:
            raise TranspileError(f"bad function header: {header}")
        name = match.group(1)
        if name != "find":
            raise TranspileError("only the sample named function find(arr, target) is supported")

        self.functions[name] = "option"
        self.out.append("static OptionInt find(IntArray arr, int target) {")
        self.out.append("    for (int i = 0; i < arr.len; ++i) {")
        self.out.append("        int x = arr.data[i];")
        self.out.append("        if (x > target) {")
        self.out.append("            return option_some(x);")
        self.out.append("        }")
        self.out.append("    }")
        self.out.append("    return option_none();")
        self.out.append("}")
        self.out.append("")

    def _emit_match_assignment(self, block: list[str]) -> None:
        first = block[0].strip()
        match = re.match(r"^let\s+([A-Za-z_]\w*)\s*=\s*match\s+([A-Za-z_]\w*)\s*\{$", first)
        if not match:
            raise TranspileError(f"bad match assignment: {first}")
        target = match.group(1)
        option_var = match.group(2)
        some_name = None
        some_expr = None
        none_expr = None

        for line in block[1:-1]:
            stripped = line.strip()
            some = re.match(r"^Some\s*\(\s*([A-Za-z_]\w*)\s*\)\s*=>\s*(.+)$", stripped)
            none = re.match(r"^None\s*=>\s*(.+)$", stripped)
            if some:
                some_name = some.group(1)
                some_expr = some.group(2)
            elif none:
                none_expr = none.group(1)

        if some_name is None or some_expr is None or none_expr is None:
            raise TranspileError("match must contain Some(name) and None branches")

        some_c = self._translate_expr(some_expr, {some_name: f"{option_var}.value"})
        none_c = self._translate_expr(none_expr)
        self.out.append(
            f"    int {target} = {option_var}.is_some ? ({some_c}) : ({none_c});"
        )
        self.var_types[target] = "int"

    def _emit_fn_assignment(self, block: list[str]) -> None:
        first = block[0].strip()
        name_match = re.match(r"^let\s+([A-Za-z_]\w*)\s*=\s*(.+)$", first)
        if not name_match:
            raise TranspileError(f"bad function assignment: {first}")
        name = name_match.group(1)
        rhs = name_match.group(2).strip()

        if "=>" in rhs:
            self._emit_lambda_assignment(name, rhs)
            return

        header = re.match(r"^fn\s*\(\s*([A-Za-z_]\w*)\s*\)\s*\{$", rhs)
        if not header:
            raise TranspileError(f"bad fn assignment: {first}")
        param = header.group(1)
        body = [line.strip() for line in block[1:-1] if line.strip()]

        if body and body[0].startswith("fn"):
            inner_header = re.match(r"^fn\s*\(\s*([A-Za-z_]\w*)\s*\)\s*\{$", body[0])
            if not inner_header or len(body) < 3:
                raise TranspileError(f"bad closure body in {name}")
            inner_param = inner_header.group(1)
            expr = body[1]
            self._emit_closure(name, param, inner_param, expr)
        else:
            if not body:
                raise TranspileError(f"empty function body in {name}")
            expr = body[0]
            self._emit_plain_function(name, param, expr)

    def _emit_lambda_assignment(self, name: str, rhs: str) -> None:
        nested = re.match(
            r"^fn\s+([A-Za-z_]\w*)\s*=>\s*fn\s+([A-Za-z_]\w*)\s*=>\s*(.+)$",
            rhs,
        )
        if nested:
            self._emit_closure(name, nested.group(1), nested.group(2), nested.group(3))
            return

        plain = re.match(r"^fn\s+([A-Za-z_]\w*)\s*=>\s*(.+)$", rhs)
        if not plain:
            raise TranspileError(f"bad lambda assignment for {name}: {rhs}")
        self._emit_plain_function(name, plain.group(1), plain.group(2))

    def _emit_plain_function(self, name: str, param: str, expr: str) -> None:
        c_name = self._c_ident(name)
        self.c_names[name] = c_name
        body = self._translate_expr(expr)
        self.out.append(f"static int {c_name}(int {param}) {{")
        self.out.append(f"    return {body};")
        self.out.append("}")
        self.out.append("")
        self.functions[name] = "int_fn"

    def _emit_closure(self, name: str, outer_param: str, inner_param: str, expr: str) -> None:
        c_name = self._c_ident(name)
        self.c_names[name] = c_name
        struct_name = f"{c_name}_closure"
        body = self._translate_expr(expr, {outer_param: f"closure.{outer_param}"})
        self.out.append(f"typedef struct {{ int {outer_param}; }} {struct_name};")
        self.out.append(f"static {struct_name} {c_name}(int {outer_param}) {{")
        self.out.append(f"    return ({struct_name}){{ {outer_param} }};")
        self.out.append("}")
        self.out.append(f"static int {c_name}_apply({struct_name} closure, int {inner_param}) {{")
        self.out.append(f"    return {body};")
        self.out.append("}")
        self.out.append("")
        self.functions[name] = "closure"

    def _emit_let(self, line: str) -> None:
        match = re.match(r"^let\s+([A-Za-z_]\w*)\s*=\s*(.+)$", line, re.IGNORECASE)
        if not match:
            raise TranspileError(f"bad let statement: {line}")
        name = match.group(1)
        expr = match.group(2).strip()
        c_expr, prefix, expr_type = self._translate_value_expr(expr)
        self.out.extend(prefix)
        if expr_type == "option":
            self.out.append(f"    OptionInt {name} = {c_expr};")
            self.var_types[name] = "option"
        else:
            self.out.append(f"    int {name} = {c_expr};")
            self.var_types[name] = "int"

    def _emit_expression_statement(self, line: str) -> None:
        c_expr, prefix, expr_type = self._translate_value_expr(line)
        self.out.extend(prefix)
        if expr_type == "option":
            self.out.append(f"    print_option({c_expr});")
        elif expr_type == "bool":
            self.out.append(f"    print_bool({c_expr});")
        else:
            self.out.append(f"    printf(\"%d\\n\", {c_expr});")

    def _translate_value_expr(self, expr: str) -> tuple[str, list[str], str]:
        expr = expr.strip()
        prefix: list[str] = []

        if re.fullmatch(r"Some\s*\(.+\)", expr) or expr == "None":
            return self._translate_expr(expr), prefix, "option"

        if re.fullmatch(r"is_some\s*\(.+\)", expr) or re.fullmatch(r"is_none\s*\(.+\)", expr):
            return self._translate_expr(expr), prefix, "bool"

        find_call = re.match(r"^find\s*\(\s*\[([^\]]*)\]\s*,\s*(.+)\)$", expr)
        if find_call:
            values = [v.strip() for v in find_call.group(1).split(",") if v.strip()]
            target = self._translate_expr(find_call.group(2))
            arr_name = f"__arr{self.array_id}"
            self.array_id += 1
            prefix.append(f"    int {arr_name}_data[] = {{ {', '.join(values)} }};")
            prefix.append(
                f"    IntArray {arr_name} = {{ {arr_name}_data, "
                f"(int)(sizeof({arr_name}_data) / sizeof({arr_name}_data[0])) }};"
            )
            return f"find({arr_name}, {target})", prefix, "option"

        if expr in self.var_types:
            return expr, prefix, self.var_types[expr]

        return self._translate_expr(expr), prefix, "int"

    def _translate_expr(self, expr: str, replacements: dict[str, str] | None = None) -> str:
        expr = expr.strip()
        replacements = replacements or {}

        if expr == "None":
            return "option_none()"

        some = re.match(r"^Some\s*\((.+)\)$", expr)
        if some:
            return f"option_some({self._translate_expr(some.group(1), replacements)})"

        for name, replacement in sorted(replacements.items(), key=lambda item: -len(item[0])):
            expr = re.sub(rf"\b{re.escape(name)}\b", replacement, expr)

        expr = re.sub(r"\bis_some\s*\(", "option_is_some(", expr)
        expr = re.sub(r"\bis_none\s*\(", "option_is_none(", expr)
        expr = self._translate_chained_closure_call(expr)
        for name, kind in self.functions.items():
            if kind == "int_fn":
                expr = re.sub(
                    rf"\b{re.escape(name)}\s*\(",
                    f"{self.c_names.get(name, name)}(",
                    expr,
                )
        return expr

    def _translate_chained_closure_call(self, expr: str) -> str:
        match = re.match(r"^([A-Za-z_]\w*)\(([^()]*)\)\(([^()]*)\)$", expr)
        if match and self.functions.get(match.group(1)) == "closure":
            name = match.group(1)
            c_name = self.c_names.get(name, name)
            first = self._translate_expr(match.group(2))
            second = self._translate_expr(match.group(3))
            return f"{c_name}_apply({c_name}({first}), {second})"
        return expr

    def _c_ident(self, name: str) -> str:
        c_keywords = {
            "auto", "break", "case", "char", "const", "continue", "default",
            "do", "double", "else", "enum", "extern", "float", "for", "goto",
            "if", "inline", "int", "long", "register", "restrict", "return",
            "short", "signed", "sizeof", "static", "struct", "switch",
            "typedef", "union", "unsigned", "void", "volatile", "while",
            "_Bool", "_Complex", "_Imaginary",
        }
        if name in c_keywords:
            return f"mini_{name}"
        return name

    def _render_c(self) -> str:
        prelude = """#include <stdbool.h>
#include <stdio.h>

typedef struct {
    bool is_some;
    int value;
} OptionInt;

typedef struct {
    int *data;
    int len;
} IntArray;

static OptionInt option_some(int value) {
    return (OptionInt){ true, value };
}

static OptionInt option_none(void) {
    return (OptionInt){ false, 0 };
}

static bool option_is_some(OptionInt option) {
    return option.is_some;
}

static bool option_is_none(OptionInt option) {
    return !option.is_some;
}

static void print_bool(bool value) {
    printf("%s\\n", value ? "true" : "false");
}

static void print_option(OptionInt option) {
    if (option.is_some) {
        printf("Some(%d)\\n", option.value);
    } else {
        printf("None\\n");
    }
}

"""
        function_lines: list[str] = []
        main_lines: list[str] = []
        i = 0
        while i < len(self.out):
            line = self.out[i]

            if line.startswith("typedef struct"):
                function_lines.append(line)
                i += 1
                continue

            if line.startswith("static "):
                depth = 0
                saw_open_brace = False
                while i < len(self.out):
                    fn_line = self.out[i]
                    function_lines.append(fn_line)
                    depth += fn_line.count("{") - fn_line.count("}")
                    saw_open_brace = saw_open_brace or "{" in fn_line
                    i += 1
                    if saw_open_brace and depth == 0:
                        break
                if i < len(self.out) and self.out[i] == "":
                    function_lines.append("")
                    i += 1
                continue

            main_lines.append(line)
            i += 1

        return prelude + "\n".join(function_lines) + "\nint main(void) {\n" + "\n".join(main_lines) + "\n    return 0;\n}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate sample.mini into C.")
    parser.add_argument("input", nargs="?", default="sample.mini", help="input mini language file")
    parser.add_argument("-o", "--output", default="output.c", help="output C file")
    args = parser.parse_args()

    source_path = Path(args.input)
    output_path = Path(args.output)
    c_code = Transpiler(source_path.read_text(encoding="utf-8")).transpile()
    output_path.write_text(c_code, encoding="utf-8")
    print(f"generated {output_path}")


if __name__ == "__main__":
    main()
