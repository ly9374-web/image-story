import ast
import importlib
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"


def find_python_files():
    return sorted(APP_DIR.rglob("*.py"))


def module_name_from_path(path):
    relative = path.relative_to(ROOT).with_suffix("")
    return ".".join(relative.parts)


def check_python39_incompatible_syntax(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    issues = []

    if "| None" in text:
        issues.append("发现 Python 3.10+ 写法：| None")

    if "list[" in text:
        issues.append("可能发现 Python 3.9 不兼容写法：list[...]")

    if "dict[" in text:
        issues.append("可能发现 Python 3.9 不兼容写法：dict[...]")

    if "tuple[" in text:
        issues.append("可能发现 Python 3.9 不兼容写法：tuple[...]")

    return issues


def check_ast_parse(path):
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        ast.parse(source)
        return None
    except Exception:
        return traceback.format_exc()


def check_import(module_name):
    try:
        importlib.import_module(module_name)
        return None
    except Exception:
        return traceback.format_exc()


def main():
    files = find_python_files()

    print("====== 1. Python 3.9 兼容性扫描 ======")
    compatibility_count = 0

    for path in files:
        issues = check_python39_incompatible_syntax(path)
        if issues:
            compatibility_count += len(issues)
            print(f"\n{path.relative_to(ROOT)}")
            for issue in issues:
                print("  -", issue)

    if compatibility_count == 0:
        print("没有发现明显的 Python 3.9 类型写法问题。")

    print("\n====== 2. 语法检查 ======")
    syntax_errors = 0

    for path in files:
        error = check_ast_parse(path)
        if error:
            syntax_errors += 1
            print(f"\n❌ 语法错误：{path.relative_to(ROOT)}")
            print(error)

    if syntax_errors == 0:
        print("所有 .py 文件语法检查通过。")

    print("\n====== 3. 模块导入检查 ======")
    import_errors = 0

    for path in files:
        module_name = module_name_from_path(path)

        error = check_import(module_name)
        if error:
            import_errors += 1
            print(f"\n❌ 导入失败：{module_name}")
            print(error)

    if import_errors == 0:
        print("所有模块导入检查通过。")

    print("\n====== 总结 ======")
    print("Python 3.9 兼容问题数量：", compatibility_count)
    print("语法错误文件数量：", syntax_errors)
    print("导入失败模块数量：", import_errors)

    if compatibility_count == 0 and syntax_errors == 0 and import_errors == 0:
        print("\n✅ 基础检查通过。现在可以运行：python3 main.py")
    else:
        print("\n⚠️ 先修上面列出的错误，再运行 python3 main.py")


if __name__ == "__main__":
    main()