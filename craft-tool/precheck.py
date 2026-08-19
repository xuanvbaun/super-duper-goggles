# -*- coding: utf-8 -*-
"""启动前自检：运行.bat 会先调用本脚本。
检查 Python 可用性、依赖库、模板、修正文件、项目文件夹，
有问题直接显示中文原因，不甩 Python 堆栈。
用法: python precheck.py [项目文件夹路径(可选)]
"""
import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(SCRIPT_DIR, '工艺清单标准模版-2026.6.30(1).xlsx')
CORRECTIONS = os.path.join(SCRIPT_DIR, 'rules', 'corrections.json')
DEPS = [
    ('pypdfium2', 'PDF 渲染'),
    ('rapidocr_onnxruntime', 'OCR 识别'),
    ('openpyxl', 'Excel 读写'),
    ('pdfminer', '文字型 PDF 提取'),
    ('pdfplumber', '文字型 PDF 表格'),
]


def check(name, ok, hint=''):
    print(f'  [{"√" if ok else "×"}] {name}' + (f'  <- {hint}' if hint and not ok else ''))
    return ok


def main():
    folder = sys.argv[1].strip().strip('"') if len(sys.argv) > 1 else ''
    ok_all = True
    print('工艺清单生成程序 - 启动自检')
    print('=' * 46)

    # 1. Python
    ver_ok = sys.version_info >= (3, 8)
    ok_all &= check('Python 可用', ver_ok, f'{sys.version.split()[0]}（需 3.8 及以上）' if not ver_ok else sys.version.split()[0])

    # 2. 依赖库
    for mod, what in DEPS:
        try:
            __import__(mod)
            ok_all &= check(f'依赖库 {mod}', True)
        except Exception:
            ok_all &= check(f'依赖库 {mod}', False,
                            f'{what}需要。请先安装：python -m pip install -r requirements.txt')

    # 3. 模板
    if os.path.exists(TEMPLATE):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(TEMPLATE)
            ok_all &= check('模板文件', '模板表单' in wb.sheetnames,
                            '模板里找不到"模板表单"工作表，请使用标准模板')
        except Exception:
            ok_all &= check('模板文件', False,
                            '无法打开（可能被 WPS 加密损坏）。请从有效副本恢复模板文件')
    else:
        ok_all &= check('模板文件', False, '文件不存在，请确认 工艺清单标准模版-2026.6.30(1).xlsx 在程序目录里')

    # 4. 修正文件
    if os.path.exists(CORRECTIONS):
        try:
            with open(CORRECTIONS, encoding='utf-8') as f:
                data = json.load(f)
            ok_all &= check('修正文件 corrections.json', isinstance(data.get('corrections'), list),
                            '缺少 corrections 列表，请检查文件格式')
        except Exception:
            ok_all &= check('修正文件 corrections.json', False, 'JSON 格式错误，请检查文件内容')
    else:
        ok_all &= check('修正文件 corrections.json', False,
                        '文件缺失，请确认 rules\\corrections.json 在程序目录里')

    # 5. 项目文件夹（传入时才检查；未传入则运行 run.py 时再校验）
    if folder:
        if os.path.isdir(folder):
            ok_all &= check('项目文件夹', True)
            pdfs = [f for f in os.listdir(folder) if f.lower().endswith('.pdf')]
            ok_all &= check('文件夹内有主清单 PDF', len(pdfs) > 0,
                            '主清单 PDF 需放在文件夹根目录（子件放在"分"子文件夹）')
        else:
            ok_all &= check('项目文件夹', False, '不是有效的文件夹路径，请检查输入')

    print('=' * 46)
    if ok_all:
        print('自检通过，可以开始生成。')
        return 0
    print('存在上述问题：请按提示处理后重新运行。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
