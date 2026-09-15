# -*- coding: utf-8 -*-
"""自动找出装有全部依赖库的 Python，并输出它的完整路径。
供 运行.bat 调用：机器上可能装了多个 Python（如 3.12 和 3.11），
依赖库只装在其中一个里，这个脚本负责把它挑出来。

用法: python find_python.py
输出: 一行 python.exe 完整路径（例如 C:/Users/.../Python311/python.exe）
找不到时无输出，以退出码 1 结束。
"""
import os
import re
import subprocess
import sys
import glob

DEPS = ('pypdfium2', 'rapidocr_onnxruntime', 'openpyxl', 'pdfminer', 'pdfplumber')
TEST_CODE = 'import ' + ', '.join(DEPS)


def has_deps(exe):
    """该解释器能否导入全部依赖库"""
    try:
        r = subprocess.run([exe, '-c', TEST_CODE],
                           capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def main():
    found = None
    # 1. 通过 py 启动器枚举所有已安装版本（从新到旧，挑第一个依赖齐全的）
    try:
        r = subprocess.run(['py', '-0p'], capture_output=True,
                           text=True, timeout=30)
        for line in r.stdout.splitlines():
            m = re.match(r'\s*-V:\d+(?:\.\d+)?\s*\*?\s*(.+)', line)
            if not m:
                continue
            exe = m.group(1).strip()
            if has_deps(exe):
                found = exe
                break
    except Exception:
        pass

    # 2. py 启动器可能注册损坏，但实际 Python 仍完整存在；直接扫描常见安装目录。
    if found is None:
        candidates = []
        local_app = os.environ.get('LOCALAPPDATA')
        if local_app:
            candidates.extend(glob.glob(os.path.join(
                local_app, 'Programs', 'Python', 'Python*', 'python.exe')))
        candidates.extend(glob.glob(r'C:\Python*\python.exe'))
        for exe in sorted(set(candidates), reverse=True):
            if has_deps(exe):
                found = exe
                break

    # 3. 兜底：正在运行本脚本的解释器
    if found is None and has_deps(sys.executable):
        found = sys.executable
    if found is None:
        return 1
    try:
        sys.stdout.reconfigure(encoding='gbk', errors='replace')
    except Exception:
        pass
    print(os.path.normpath(found))
    return 0


if __name__ == '__main__':
    sys.exit(main())
