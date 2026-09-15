# -*- coding: utf-8 -*-
"""工艺清单生成程序（可移植版）
用法:
    python run.py "图纸材料表PDF所在文件夹"
    或直接双击 运行.bat 后输入文件夹路径

流程: 扫描源文件夹(一个或多个顶层PDF + 分/子件PDF) -> OCR -> 表格重建 -> 生成工艺清单Excel
输出: 单根清单沿用设备名称；多个独立顶层清单合并为同文件夹的一份“总清单”。
"""
import os, sys, re, json, hashlib, shutil
from collections import defaultdict, Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(SCRIPT_DIR, '工艺清单标准模版-2026.6.30(1).xlsx')
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')

INT_RE = re.compile(r'^(\d+)')
FLOAT_RE = re.compile(r'\d+\.\d+|\d+')
DRAW_RE = re.compile(r'[A-Z0-9]{2,6}-[A-Z0-9]{2,6}-\d{2,4}(?:-\d{2,4})?')
JUNK_RE = re.compile(r'模板文件|第\d+页|^\d{4}/\d+/\d+|26X-R\d+|26X-k\d+|26X-K\d+')
# 发图登记表/图纸清单是发图纸的登记性文件，不是图纸材料表：OCR 解析不出材料表号，
# 也没有明细行。阿瑞斯每批发图都带一份，放在清单文件夹里时不能当主清单（否则只输出空行）。
REGISTRY_RE = re.compile(r'登记表|发图清单|图纸清单|发图记录')

# 表格列边界（PDF 页面统一渲染为 1685x1192）
# 旧模板：数量列在 x≈245；新模板（Q300 销钉焊接图、Q281 变体）：左列左移/右列右移
BOUNDS_A = [
    ('seq', 245), ('qty', 305), ('unit', 340), ('name', 570), ('spec', 950),
    ('std', 1160), ('material', 1315), ('weight', 1415), ('supplier', 1470), ('cat', 99999),
]
BOUNDS_B = [
    # 阿瑞斯新版表格的“名称/规格”竖线约在 x=500；旧值565会把规格栏开头
    # （如“带法兰密封垫”“Ø354/Ø284x4”）错误拼进名称。
    ('seq', 210), ('qty', 280), ('unit', 315), ('name', 500), ('spec', 950),
    ('std', 1160), ('material', 1330), ('weight', 1440), ('supplier', 1510), ('cat', 99999),
]

def pick_bounds(lines, h_yc):
    """按表头'数量'列的位置选择模板列边界（旧 x≈245 / 新 x≈215）"""
    for l in lines:
        if abs(l[1] - h_yc) <= 40 and l[6] == '数量':
            return BOUNDS_B if l[0] < 240 else BOUNDS_A
    return BOUNDS_A

def col_of(xc, bounds=BOUNDS_A):
    for cn, b in bounds:
        if xc < b:
            return cn
    return 'cat'

PROFILE_KEYS = ('角钢', '方钢', '空心钢', '槽钢', '工字钢', 'H型钢', '扁钢')

# ============================== 基础工具 ==============================
def parse_int(t):
    m = INT_RE.match(t or '')
    return int(m.group(1)) if m else None

def parse_float(t):
    m = FLOAT_RE.search(t or '')
    return float(m.group(0)) if m else None

def clean_spec(t):
    t = re.sub(r"(?<=\d)'(?=\d)", '1', t)  # OCR 常把数字间的 1 读成撇号（如 L=311'5 → L=3115）
    t = re.sub(r'口(?=\d)|(?<=\d)口', '□', t).replace('?', '')  # 方钢符号□(OCR常读成口)，中文"口"不替换
    t = re.sub(r'(?<=\d):(?=\d)', '.', t)       # 冒号误读小数点（2:8→2.8）
    t = re.sub(r'(?<=\D)Q(?=\d)', 'Ø', t)       # Q 误读 Ø（Q26.9→Ø26.9）
    t = re.sub(r',(?=\s*\d)', ' ', t)           # 逗号后接数字是噪声（DN20, 026.9→DN20 026.9）
    t = re.sub(r'(^|[\s,])(==+|b=|=)(?=\d)', r'\1L=', t)  # =/==/b= 误读 L=（=1205→L=1205）
    t = re.sub(r'<=(?=\d)', 'L=', t)                  # <= 误读 L=（<=200→L=200）
    t = re.sub(r'K=(\d+)(?![°度]|\.\d|\d)', r'L=\1', t)   # K 误读 L（K=40→L=40，保留销轴 K=120°）
    t = re.sub(r'L=(\d+)Q(?=\D|$)', r'L=\g<1>0', t)      # L=173Q→L=1730（Q误读0）
    t = re.sub(r'L=(\d)\.(\d)(\d)', r'L=\1\2\3', t)      # L=8.50→L=850, L=1.070→L=1070
    t = t.replace('ⅡI', 'Ⅱ')
    t = t.replace('平热', '平垫').replace('弹热', '弹垫')
    t = re.sub(r'(?<=\d)\s+(?=\d(?:\D|$))', '.', t)  # 3 5→3.5（小数点漏识别）
    t = re.sub(r'^0(?=\d{3,4}/)', 'Ø', t)              # 01100/Ø817→Ø1100/Ø817
    t = t.replace('L=1.6', 'L=16')
    t = re.sub(r'(?<=\d)X(?=\d)', 'x', t)
    ls = re.findall(r'L=\d+(?:\.\d+)?', t)
    rest = re.sub(r'L=\d+(?:\.\d+)?', '', t)
    rest = re.sub(r'(?<![\d.])0(\d{2,3})(?![\d])', r'Ø\1', rest)
    out = re.sub(r'\s+', ' ', rest).strip()
    # OCR 把单元格内换行读成空格时，中文之间会多出空格（“外螺 纹”），中文之间不留空格
    out = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', out)
    return (out + ' ' + ' '.join(ls)).strip()

def clean_name(t):
    t = t.replace('(', '（').replace(')', '）')
    t = t.replace('0型', 'O型')
    t = t.replace('层步梯组装图', '二层步梯组装图')   # OCR 漏"二"字
    t = re.sub(r'\(带\s*侧喷口[）)]', '(带侧喷口)', t)
    t = re.sub(r'（带\s*侧喷口[）)]', '(带侧喷口)', t)
    t = t.replace('烟肉', '烟囱').replace('烟卤', '烟囱')
    return t.strip()

def clean_std(t):
    t = t.replace('7Q.1', '70.1')
    t = re.sub(r'^[>＞]+', '', t)
    return t.strip()

def normalize_mat(t):
    t = t.replace('（', '(').replace('）', ')')
    return re.sub(r'\s+', '', t)

def normalize_drawing(d):
    return re.sub(r'-[A-Z]$', '', d)

def draw_sort_key(d):
    """图号自然排序键：GDL161-300-09 排在 -10 之前，多根合并顺序才稳定。"""
    return [(1, int(p)) if p.isdigit() else (0, p) for p in re.split(r'(\d+)', d or '')]

def refs_of(r):
    return re.findall(DRAW_RE, r.get('std', ''))

def line_center(box):
    xs = [p[0] for p in box]; ys = [p[1] for p in box]
    return (min(xs)+max(xs))/2, (min(ys)+max(ys))/2

def line_box(box):
    xs = [p[0] for p in box]; ys = [p[1] for p in box]
    return min(xs), min(ys), max(xs), max(ys)

# ============================== 源文件扫描 ==============================
def drawing_from_filename(f):
    m = re.search(DRAW_RE, f)
    if m:
        return m.group(0)
    return normalize_drawing(re.sub(r'[（(].*?[)）]', '', f).strip())

def scan_sub_pdfs(folder):
    """扫描一个文件夹里的子件PDF，返回 {规范化图号: 路径}"""
    out = {}
    if not os.path.isdir(folder):
        return out
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith('.pdf'):
            continue
        d = drawing_from_filename(f)
        if d in out and re.search(r'Q281', f):
            continue  # 已有同图号PDF时忽略 Q281 变体（主清单引用 Q280 基础版）
        out[d] = os.path.join(folder, f)
    return out

def find_project(source_dir):
    """返回 (兼容主PDF, 可展开PDF映射, 顶层PDF列表)。

    顶层PDF不能只挑第一份：它们可能是多个独立根清单，也可能互相引用形成
    多棵装配树。第一份仅保留为旧流程的缓存入口，最终根清单由引用关系决定。
    """
    source_dir = os.path.abspath(source_dir)
    if not os.path.isdir(source_dir):
        print(f'错误: 文件夹不存在 -> {source_dir}')
        sys.exit(1)

    pdfs_top = sorted(f for f in os.listdir(source_dir) if f.lower().endswith('.pdf'))
    sub_pdfs = scan_sub_pdfs(os.path.join(source_dir, '分'))
    # 跨项目回退：在源文件夹的上级目录里查找同图号的子件PDF（如 A300 引用 GDL130-Q300-20）
    # 本项目 分 优先，兄弟项目只做缺失回退（setdefault 不覆盖已存在的同图号）
    parent = os.path.dirname(source_dir)
    if os.path.isdir(parent):
        for d in os.listdir(parent):
            dp = os.path.join(parent, d)
            if not os.path.isdir(dp) or d == os.path.basename(source_dir):
                continue
            if d == '分':  # 同级的分文件夹本身就是另一个项目的子件目录
                ext = scan_sub_pdfs(dp)
            else:          # 兄弟项目文件夹内的 分
                ext = scan_sub_pdfs(os.path.join(dp, '分'))
            for k, v in ext.items():
                sub_pdfs.setdefault(k, v)

    main_pdf = None
    if pdfs_top:
        # 登记表类文件优先排除；都排除了才退回用它们（此时 run() 会改从 分\ 里的
        # 独立材料表按引用关系选根，不会把登记表当清单输出）。
        lists = [f for f in pdfs_top if not REGISTRY_RE.search(f)]
        cand = [f for f in lists if '总图' in f] or lists
        main_pdf = os.path.join(source_dir, (cand or pdfs_top)[0])
    if main_pdf is None:
        print('错误: 源文件夹中没有找到 PDF 文件')
        sys.exit(1)
    top_paths = [os.path.join(source_dir, f) for f in pdfs_top]
    # 其余顶层PDF也必须进入OCR和子图映射。之后再通过引用图构建真正的根清单，
    # 可同时支持“多棵独立装配树”和“若干完全无层级PDF”。
    main_key = os.path.normcase(os.path.abspath(main_pdf))
    for p in top_paths:
        if os.path.normcase(os.path.abspath(p)) == main_key:
            continue
        sub_pdfs.setdefault(normalize_drawing(drawing_from_filename(os.path.basename(p))), p)
    return main_pdf, sub_pdfs, top_paths

# ============================== OCR 步骤 ==============================
def do_ocr(pdf_path, cache_dir, name):
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    print(f'  [OCR] {os.path.basename(pdf_path)} ...')
    try:
        pdf = pdfium.PdfDocument(pdf_path)
    except Exception:
        print(f'  [跳过] 无法读取PDF（可能被WPS损坏）: {os.path.basename(pdf_path)}')
        return None
    ocr = RapidOCR()
    out = {'file': pdf_path, 'pages': []}
    for i in range(len(pdf)):
        img = pdf[i].render(scale=2.0).to_pil()
        tmp = os.path.join(cache_dir, f'{name}_p{i}.png')
        img.save(tmp)
        res, _ = ocr(tmp)
        page = [{'box': it[0], 'text': it[1], 'conf': float(it[2])} for it in (res or [])]
        out['pages'].append(page)
        print(f'  [OCR]   页{i+1}: {len(page)} 行')
        os.remove(tmp)  # 只保留识别结果，不保留临时图片
    with open(os.path.join(cache_dir, name + '.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    return out

# ============================== 表格重建 ==============================
def meta_of(doc, page_index=0):
    """读取指定页的材料表元数据。

    一个 PDF 可能是多张独立材料表与图纸合订而成；元数据不能固定只读首页。
    """
    pages = doc.get('pages') or []
    if page_index < 0 or page_index >= len(pages):
        return {}
    joined = '\n'.join(it['text'] for it in pages[page_index])
    m = {}
    for key, pat in [('drawing', r'材料表号[:：]?\s*([A-Za-z0-9\-]+)'),
                     ('qty', r'制造数量：?\s*([0-9]+)'),
                     ('name', r'设备名称：?\s*([^\n]+)'),
                     ('contract', r'合同号：?\s*([^\n]+)')]:
        mm = re.search(pat, joined)
        if mm:
            value = mm.group(1).strip()
            m[key] = clean_name(value) if key == 'name' else value
    return m

def parse_page(page):
    lines = []
    for it in page:
        box, text, conf = it['box'], it['text'], it['conf']
        xc, yc = line_center(box)
        x0, y0, x1, y1 = line_box(box)
        lines.append((xc, yc, y0, y1, x0, x1, text, conf))
    header = next((l for l in lines if l[6] == '名称'), None)
    if header is None:
        header = next((l for l in lines if '名称' in l[6]), None)
    if header is None:
        return None
    h_yc = header[1]
    bounds = pick_bounds(lines, h_yc)
    h_bottom = h_yc + 30
    data = [l for l in lines if l[1] > h_bottom and l[4] > 60 and not JUNK_RE.search(l[6])]
    if not data:
        return []
    data.sort(key=lambda l: l[1])
    bands, cur = [], [data[0]]
    for l in data[1:]:
        if l[1] - cur[-1][1] < 13.5:
            cur.append(l)
        else:
            bands.append(cur); cur = [l]
    bands.append(cur)
    rows = []
    for band in bands:
        rec = {'y': (min(l[1] for l in band) + max(l[1] for l in band)) / 2, 'cols': defaultdict(list)}
        for l in band:
            rec['cols'][col_of(l[0], bounds)].append((l[6], l[7], l[2]))
        rows.append(rec)
    return rows

def build_tables(cache_dir, only_names=None):
    """读取缓存目录里的 OCR 结果重建表格。
    only_names: 只读取这些缓存名（本次实际扫描到的 PDF），防止已删除子件的旧缓存污染结果。"""
    results = {}
    for f in sorted(os.listdir(cache_dir)):
        if not f.endswith('.json'):
            continue
        name = f[:-5]
        if only_names is not None and name not in only_names:
            continue
        with open(os.path.join(cache_dir, f), encoding='utf-8') as fh:
            doc = json.load(fh)
        groups = []
        current = None
        for pi, page in enumerate(doc['pages']):
            rows = parse_page(page)
            if rows is None:
                continue
            page_meta = meta_of(doc, pi)
            page_drawing = normalize_drawing(page_meta.get('drawing', ''))
            current_drawing = normalize_drawing(current['meta'].get('drawing', '')) if current else ''
            page_name = clean_name(page_meta.get('name', ''))
            current_name = clean_name(current['meta'].get('name', '')) if current else ''
            # 每个带“材料表号”的新表头都是一张独立清单；没有材料表号的后续页
            # 仍视为上一张表的续页。登记表和普通图纸因没有材料表表头会被跳过。
            new_table = bool(
                current is None
                or (page_drawing and page_drawing != current_drawing)
                or (not page_drawing and page_name and current_name and page_name != current_name)
            )
            if new_table:
                current = {
                    'records': [], 'meta': page_meta, 'total_weight': None,
                    'source_pages': [], 'start_page': pi,
                }
                groups.append(current)
            else:
                for key, value in page_meta.items():
                    current['meta'].setdefault(key, value)
            current['source_pages'].append(pi)
            for r in rows:
                rec = {}
                for cn in ('seq','qty','unit','name','spec','std','material','weight','supplier','cat'):
                    if cn in r['cols']:
                        vals = sorted(r['cols'][cn], key=lambda v: v[2])
                        text = re.sub(r'\s+', ' ', ' '.join(v[0] for v in vals)).strip()
                        if text:
                            rec[cn] = (text, min(v[1] for v in vals))
                for k in rec:
                    m = re.search(r'总重[：:]\s*([\d.]+)', rec[k][0])
                    if m:
                        current['total_weight'] = float(m.group(1))  # 本张材料表页脚总重
                if len(rec) == 1 and 'weight' in rec:
                    continue
                if any('总重' in rec[k][0] for k in rec):
                    continue
                if set(rec.keys()) <= {'supplier', 'cat'}:
                    continue
                rec['_page'] = pi
                rec['_y'] = r['y']
                current['records'].append(rec)
        if not groups:
            results[name] = {'file': doc['file'], 'records': [], 'meta': meta_of(doc),
                             'total_weight': None, 'pages': doc.get('pages', []),
                             'source_name': name, 'source_pages': []}
            continue
        multiple = len(groups) > 1
        for group in groups:
            key = f"{name}__P{group['start_page'] + 1:03d}" if multiple else name
            results[key] = {
                'file': doc['file'], 'records': group['records'], 'meta': group['meta'],
                'total_weight': group['total_weight'], 'pages': doc.get('pages', []),
                'source_name': name, 'source_pages': group['source_pages'],
            }
    return results

# ============================== PART/WEIGHT REREAD ==============================
WEIGHT_RE = re.compile(r'^\d+(?:\.\d{1,4})?$')
PART_RE = re.compile(r'^\d+(?:\.\d+)*$')
QTY_RE = re.compile(r'\d+(?:\.\d+)?')

def _clean_weight(val):
    s = (val or '').strip().replace('，', ',').replace('．', '.')
    s = re.sub(r'(?<=\d)\s*([.,])\s*(?=\d)', r'\1', s)
    s = re.sub(r'\s*(?:kg|千克|公斤)\s*$', '', s, flags=re.I)
    # 逗号后恰为三位时，无法判定是千位分隔还是小数，交给人工确认。
    if re.fullmatch(r'\d+,\d{3}', s):
        return None
    s = s.replace(',', '.')
    if WEIGHT_RE.fullmatch(s):
        try:
            return float(s)
        except ValueError:
            return None
    return None

def _clean_part_no(val):
    s = re.sub(r'\s+', '', (val or '').strip())
    return s if PART_RE.fullmatch(s) else None

def _clean_qty(val):
    """数量列只接受唯一的正数；允许小数数量及 OCR 带出的相邻单位文字。"""
    text = re.sub(r'\s*(?:件|个|套|米|m|pcs)\s*$', '', (val or '').strip(), flags=re.I)
    q = _clean_weight(text)
    if q is None:
        return None
    if not (0 < q <= 100000):
        return None
    return int(q) if q.is_integer() else q

def _page_lines(page):
    lines = []
    for it in page or []:
        box, text, conf = it['box'], it['text'], it['conf']
        xc, yc = line_center(box)
        x0, y0, x1, y1 = line_box(box)
        lines.append((xc, yc, y0, y1, x0, x1, text, conf))
    return lines

def _find_header(lines, keywords):
    exact = [l for l in lines if any(l[6].strip() == k for k in keywords)]
    if exact:
        return min(exact, key=lambda l: l[1])
    fuzzy = [l for l in lines if any(k in l[6].replace(' ', '') for k in keywords)]
    if fuzzy:
        return min(fuzzy, key=lambda l: l[1])
    return None

def _column_window(page, kind):
    lines = _page_lines(page)
    if not lines:
        return None

    name_h = _find_header(lines, ('名称',))
    h_yc = name_h[1] if name_h else min(l[1] for l in lines)
    bounds = pick_bounds(lines, h_yc)

    if kind == 'weight':
        cur = _find_header(lines, ('重量',))
        left_h = _find_header(lines, ('材料/物料编码', '物料编码', '材料'))
        right_h = _find_header(lines, ('供货',))
        if cur:
            cx = cur[0]
            left = (left_h[0] + cx) / 2 if left_h and left_h[0] < cx else cx - 70
            right = (cx + right_h[0]) / 2 if right_h and right_h[0] > cx else cx + 70
            return max(0, left - 8), right + 8
        prev = 0
        for cn, b in bounds:
            if cn == 'weight':
                return max(0, prev - 10), b + 10
            prev = b
        return None

    if kind == 'seq':
        # 表头常被 OCR 拆成“件”/“号”两行，不能只查完整“件号”。
        cur = _find_header(lines, ('件号', '件'))
        left_h = _find_header(lines, ('修改', '修'))
        right_h = _find_header(lines, ('数量',))
        if not cur:
            return None
        cx = cur[0]
        left = (left_h[0] + cx) / 2 if left_h and left_h[0] < cx else cx - 35
        right = (cx + right_h[0]) / 2 if right_h and right_h[0] > cx else cx + 35
        return max(0, left + 2), right - 2

    if kind == 'qty':
        cur = _find_header(lines, ('数量',))
        left_h = _find_header(lines, ('件号',))
        right_h = _find_header(lines, ('单位',))
        if not cur:
            return None
        cx = cur[0]
        left = (left_h[0] + cx) / 2 if left_h and left_h[0] < cx else cx - 28
        right = (cx + right_h[0]) / 2 if right_h and right_h[0] > cx else cx + 28
        return max(0, left + 2), right - 2

    return None

def _ocr_row_cell(img6, x0, x1, row_y, ocr, suffix, variant='enlarged', evidence=None):
    import tempfile
    from PIL import Image
    k = 3.0
    y0 = max(0, row_y - 22)
    y1 = row_y + 22
    crop = img6.crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))
    if crop.width <= 0 or crop.height <= 0:
        return []
    if evidence:
        crop.save(evidence)
    if variant == 'enlarged':
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    elif variant == 'cleaned':
        import cv2
        import numpy as np
        gray = np.array(crop.convert('L'))
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, crop.width // 2), 1)))
        vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, crop.height * 3 // 4))))
        crop = Image.fromarray(255 - cv2.subtract(ink, cv2.bitwise_or(horizontal, vertical)))
    tmp = tempfile.NamedTemporaryFile(prefix='craft_', suffix=suffix, delete=False)
    tmp.close()
    try:
        crop.save(tmp.name)
        res, _ = ocr(tmp.name)
        return [it[1].strip() for it in (res or []) if it[1].strip()]
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass

def reread_missing_part_numbers(tables):
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    filled = changed = 0
    for t in tables.values():
        pages = t.get('pages') or []
        if not pages:
            continue
        missing_by_page = {}
        for rec in t['records']:
            raw = rec.get('seq', ('', 0))[0].strip() if 'seq' in rec else ''
            if _clean_part_no(raw) is not None:
                continue
            missing_by_page.setdefault(rec.get('_page', 0), []).append(rec)
        if not missing_by_page:
            continue
        try:
            pdf = pdfium.PdfDocument(t['file'])
        except Exception:
            continue
        for pi, recs in missing_by_page.items():
            if pi >= len(pages) or pi >= len(pdf):
                continue
            win = _column_window(pages[pi], 'seq')
            if not win:
                continue
            img6 = pdf[pi].render(scale=6.0).to_pil()
            for rec in recs:
                texts = _ocr_row_cell(img6, win[0], win[1], rec['_y'], ocr, '_seq.png')
                vals = []
                for text in texts:
                    direct = _clean_part_no(text)
                    if direct:
                        vals.append(direct)
                        continue
                    found = re.findall(r'\d+(?:\.\d+)*', text)
                    if len(found) == 1 and PART_RE.fullmatch(found[0]):
                        vals.append(found[0])
                vals = [x for x in vals if x]
                uniq = list(dict.fromkeys(vals))
                if len(uniq) == 1:
                    old = _clean_part_no(raw)
                    rec['seq'] = (uniq[0], 1.0)
                    rec['_seq_reread'] = True
                    if old is None:
                        filled += 1
                    elif old != uniq[0]:
                        rec['_seq_original'] = old
                        changed += 1
    print(f"Part-number reread: corrected {changed}, filled {filled}")

def reread_missing_weights(tables):
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    filled = 0
    for t in tables.values():
        pages = t.get('pages') or []
        if not pages:
            continue
        missing_by_page = {}
        for rec in t['records']:
            if _clean_weight(rec.get('weight', ('', 0))[0]) is None:
                missing_by_page.setdefault(rec.get('_page', 0), []).append(rec)
        if not missing_by_page:
            continue
        try:
            pdf = pdfium.PdfDocument(t['file'])
        except Exception:
            continue
        for pi, recs in missing_by_page.items():
            if pi >= len(pages) or pi >= len(pdf):
                continue
            win = _column_window(pages[pi], 'weight')
            if not win:
                continue
            img6 = pdf[pi].render(scale=6.0).to_pil()
            for rec in recs:
                texts = _ocr_row_cell(img6, win[0], win[1], rec['_y'], ocr, '_weight.png')
                vals = [_clean_weight(x) for x in texts]
                vals = [x for x in vals if x is not None]
                uniq = list(dict.fromkeys(vals))
                if len(uniq) == 1:
                    rec['weight'] = (str(uniq[0]), 1.0)
                    rec['_weight_reread'] = True
                    filled += 1
    if filled:
        print("Weight reread filled:", filled)

def quantity_decision(raw, confidence, readings):
    """不把多数票当作事实：已有数值冲突时保留原值并要求复核。"""
    original = _clean_qty(raw)
    parsed = []
    for texts in readings:
        values = [_clean_qty(t) for t in texts]
        parsed.append(values[0] if len(values) == 1 else None)
    candidates = sorted({v for v in parsed if v is not None})
    unanimous = len(parsed) == 3 and all(v is not None for v in parsed) and len(candidates) == 1
    if unanimous and (original is None or original == candidates[0]):
        return candidates[0], ''
    return original, f'数量待确认：原识别={raw!r}，置信度={confidence:.2f}，三次补读={parsed}；未按多数票改数'


def reread_quantities(tables, evidence_dir=None):
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
    filled = 0
    for t in tables.values():
        pages = t.get('pages') or []
        by_page = defaultdict(list)
        for index, rec in enumerate(t['records']):
            raw, confidence = rec.get('qty', ('', 0))
            value = _clean_qty(raw)
            if value is None or confidence < 0.95 or any(c in str(value) for c in '69'):
                rec['_qty_review'] = f'数量待确认：原识别={raw!r}，尚无一致补读结果'
                by_page[rec.get('_page', 0)].append((index, rec))
        if not by_page:
            continue
        try:
            pdf = pdfium.PdfDocument(t['file'])
        except Exception:
            continue
        try:
            for pi, recs in by_page.items():
                if pi >= len(pages) or pi >= len(pdf):
                    continue
                win = _column_window(pages[pi], 'qty')
                if not win:
                    continue
                img = pdf[pi].render(scale=6.0).to_pil()
                for index, rec in recs:
                    evidence = None
                    if evidence_dir:
                        key = hashlib.md5(os.path.abspath(t['file']).encode('utf-8')).hexdigest()[:10]
                        evidence = os.path.join(evidence_dir, f'{key}_p{pi+1}_row{index+1}.png')
                        rec['_qty_evidence'] = evidence
                    readings = [_ocr_row_cell(img, win[0], win[1], rec['_y'], ocr,
                                '_qty.png', variant=v, evidence=evidence if v == 'original' else None)
                                for v in ('original', 'enlarged', 'cleaned')]
                    raw, confidence = rec.get('qty', ('', 0))
                    value, review = quantity_decision(raw, confidence, readings)
                    rec['_qty_review'] = review
                    if _clean_qty(raw) is None and value is not None:
                        rec['_qty_original'] = raw
                        rec['qty'] = (str(value), confidence)
                        filled += 1
        finally:
            pdf.close()
    print(f'数量补读：补全 {filled} 格；冲突已保留供人工确认')

# ============================== 已确认修正（外置文件） ==============================
def load_corrections():
    p = os.path.join(SCRIPT_DIR, 'rules', 'corrections.json')
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f).get('corrections', [])
    except Exception as e:
        print(f'[警告] 读取修正文件失败（将跳过已确认修正）: {p} ({e})')
        return []

CORRECTIONS = load_corrections()

def apply_corrections(records, corrections):
    """按 corrections.json 的规则修正记录。
    匹配字段：drawing(图号) / drawing_prefix(图号前缀) / drawings(图号列表) / name / spec_contains / spec_eq /
    material_eq / qty_eq / seq_raw_eq(件号原文) / weight_gt / weight_is_null；
    匹配后把 set 里的字段改为新值。"""
    for r in records:
        for c in corrections:
            if c.get('drawing') and c['drawing'] != r['doc_drawing']:
                continue
            if c.get('drawing_prefix') and not r['doc_drawing'].startswith(c['drawing_prefix']):
                continue
            if c.get('drawings') and r['doc_drawing'] not in c['drawings']:
                continue
            if c.get('name') and c['name'] != r['name']:
                continue
            if c.get('spec_contains') and not all(s in r['spec'] for s in c['spec_contains']):
                continue
            if c.get('spec_eq') is not None and r['spec'] != c['spec_eq']:
                continue
            if c.get('material_eq') is not None and r['material'] != c['material_eq']:
                continue
            if c.get('qty_eq') is not None and r['qty'] != c['qty_eq']:
                continue
            # 件号原文匹配：OCR 把 6 读成 9 这类误读，只在读到错误值时纠正；
            # 将来 OCR 本身读对了，该条修正自动失效，不会把正确件号改坏。
            if c.get('seq_raw_eq') is not None and r.get('seq_raw', '') != c['seq_raw_eq']:
                continue
            if c.get('weight_gt') is not None and not (r['weight'] is not None and r['weight'] > c['weight_gt']):
                continue
            if c.get('weight_is_null') and r['weight'] is not None:
                continue
            for k, v in c['set'].items():
                r[k] = v
            # 外置规则代表已经人工确认；规则明确修正数量后，不能继续保留
            # 此前 OCR 补读产生的“数量待确认”标记。
            if 'qty' in c['set']:
                r['qty_review'] = ''

def capture_total_weights(tables):
    """补全各材料表页脚"总重：XXX kg"：低倍率没捕获到的，对该表末页底部区域 scale6 复读。
    返回 {doc名: 总重}（仅补缺失的，已有值保留）。"""
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    from PIL import Image
    T_RE = re.compile(r'总\s*重\s*[：:]?\s*([\d.]+)')
    ocr = RapidOCR()
    out = {}
    for name, t in tables.items():
        if t.get('total_weight') is not None:
            continue
        try:
            pdf = pdfium.PdfDocument(t['file'])
        except Exception:
            continue
        try:
            source_pages = t.get('source_pages') or []
            pi = max(source_pages) if source_pages else len(pdf) - 1
            img = pdf[pi].render(scale=6.0).to_pil()
            w, h = img.size
            crop = img.crop((int(0.35 * w), int(0.55 * h), int(0.98 * w), int(0.995 * h)))
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            crop.save('_tw.png')
            res, _ = ocr('_tw.png')
            os.remove('_tw.png')
            txt = ''.join(it[1] for it in (res or []))
            m = T_RE.search(txt)
            if m:
                out[name] = float(m.group(1))
        except Exception:
            continue
    return out

# ============================== 行处理 ==============================
def process_doc(t):
    doc_drawing = normalize_drawing(t['meta'].get('drawing', ''))
    out = []
    for rec in t['records']:
        r = {
            'seq':   parse_int(rec['seq'][0]) if 'seq' in rec else None,
            'seq_raw': rec['seq'][0].strip() if 'seq' in rec else '',   # PDF原件号原文（保留 2.1 分层件号）
            'qty':   _clean_qty(rec['qty'][0]) if 'qty' in rec else None,
            'unit':  rec['unit'][0].replace('祥', '件') if 'unit' in rec else '件',
            'name':  clean_name(rec['name'][0]) if 'name' in rec else '',
            'spec':  clean_spec(rec['spec'][0]) if 'spec' in rec else '',
            'std':   clean_std(rec['std'][0]) if 'std' in rec else '',
            'material': clean_spec(rec['material'][0]) if 'material' in rec else '',
            'weight':   _clean_weight(rec['weight'][0]) if 'weight' in rec else None,
            'supplier': rec['supplier'][0].strip() if 'supplier' in rec else '',
            'cat':      rec['cat'][0].strip() if 'cat' in rec else '',
            'doc_drawing': doc_drawing,
            'ares': False,
            'qty_review': rec.get('_qty_review', ''),
            'qty_evidence': rec.get('_qty_evidence', ''),
        }
        # 新版阿瑞斯表格中“重量”和“供货”两格间距很窄，OCR 经常把它们合成
        # 一个文本框（如“23.21 Ares”或“0.12”），其中心点会落入供货列。
        # 当重量栏为空时，从这个合并框中回收重量；供货标记本身继续保留。
        if r['weight'] is None and r['supplier']:
            weight_match = re.search(r'(?<![A-Za-z0-9])\d+\.\d+(?![A-Za-z0-9])', r['supplier'])
            if weight_match:
                r['weight'] = float(weight_match.group(0))
                r['supplier'] = re.sub(r'\s+', ' ',
                                       r['supplier'][:weight_match.start()] + ' ' +
                                       r['supplier'][weight_match.end():]).strip()
        r['ares'] = 'Ares' in r['supplier']
        # OCR 偶尔把规格栏开头的管径粘到名称末尾，例如：
        # “流体输送用不锈钢无缝钢管021x3.0” + “L=300”。
        # 将末尾尺寸移回规格栏，避免输出成“圆管/材质”。
        leaked_pipe_spec = re.search(r'([0QØ]\d+(?:\.\d+)?x\d+(?:\.\d+)?)$', r['name'])
        if leaked_pipe_spec and any(k in r['name'] for k in ('钢管', '焊管', '无缝管')):
            leaked = leaked_pipe_spec.group(1)
            if leaked.startswith(('0', 'Q')):
                leaked = 'Ø' + leaked[1:]
            r['name'] = r['name'][:-len(leaked_pipe_spec.group(1))].rstrip()
            r['spec'] = clean_spec(f"{leaked} {r['spec']}")
        if not r['name'] and not r['spec'] and not r['std']:
            continue
        # 纯说明行不是物料，不能混入 Excel。说明文字有时被 OCR 分散到名称、
        # 规格或标准列，因此按整行文字识别，且仅在无件号/数量/材质/重量时跳过。
        note_text = ' '.join(x for x in (r['name'], r['spec'], r['std']) if x).strip()
        is_note = bool(re.match(r'^注\s*[：:]', note_text) or re.search(
            r'如图制作|镜像制作|实际使用数量|另加\s*\d+\s*件?备件', note_text))
        if (is_note and not _clean_part_no(r['seq_raw']) and r['qty'] is None
                and not r['material'] and r['weight'] is None):
            continue
        # 常见 OCR 修正
        r['std'] = r['std'].replace('GDL465-', 'GDL165-')
        if r['name'] == '流体输送用无缝钢管' and '146x4.0' in r['spec']:
            r['spec'] = r['spec'].replace('146x4.0', 'Ø146x4.0')   # 缺Ø(复核确认)
        # 管状卷制件的直径符号位于规格开头时，OCR 常把 Ø 读成 Q；
        # clean_spec 不能全局替换开头 Q，否则会破坏 Q235-A 这类材质牌号。
        if ('卷管' in r['name'] or '钢筒' in r['name']) and re.match(r'^Q\d+[xX]', r['spec']):
            r['spec'] = 'Ø' + r['spec'][1:]
        if r['name'] == '耐热钢板':
            if 'Q154' in r['spec']:
                r['spec'] = '2×Ø154'          # Q为0误读(复核确认)
            elif '2×154' in r['spec']:
                r['spec'] = '2×Ø154'          # 缺Ø(复核确认)
        if r['name'] == '陶瓷纤维方编绳':
            r['material'] = ''           # 材质格在PDF中为空白
        r['material'] = re.sub(r'\s*26X\S*', '', r['material']).strip()   # 合同号渗出噪声(复核确认)
        r['spec'] = re.sub(r'^\d+\s+(?=90E\(L\))', '', r['spec'])          # 90°弯头前的孤立数字噪声
        out.append(r)
    apply_corrections(out, CORRECTIONS)   # 已人工确认的修正（rules/corrections.json）
    assign_part_no(out)
    return out

SEQ_RE = re.compile(r'^\d+(\.\d+)*$')   # 合法件号格式：45 / 2.1 / 19.2

def assign_part_no(records):
    """件号 = PDF 原件号（字符串，保留 2.1 这类分层件号）。
    不因行数/重复/缺失重新编号（图纸件号是图纸标识，程序无权重编）；
    缺失或格式明显异常（如 OCR 乱码）时置 None，由复核报告标记。"""
    for r in records:
        raw = r.get('seq_raw', '')
        r['part_no'] = raw if SEQ_RE.match(raw) else None

STD_NAME_RE = re.compile(r'螺栓|螺柱|螺钉|螺母|垫圈|开口销|销轴|铆钉|挡圈|键|轴承|油杯')

def is_std_part(r):
    if refs_of(r):
        return False  # 有子图号引用的是自制件，不是标准件（分类号列常被OCR误读成16）
    if r.get('cat') in ('16', '17', '7') and '编绳' not in r.get('name', ''):
        return True
    # 分类号列常被 OCR 读坏（如 116 2 4 / 空），用"标准件名称+GB/T/JB/T标准号"兜底
    return (bool(STD_NAME_RE.search(r.get('name', ''))) and bool(re.search(r'GB/?T|JB/?T', r.get('std', '')))
            and '编绳' not in r.get('name', ''))

def number_duplicate_names(nodes):
    """同一父件下重名子件在名称后加序号区分（标准件不加），用户规则第7条。

    同一子图被多个父件引用时记录字典是共享的，用 id(row) 防重复处理，
    否则第二个父件会把 name_base 覆盖成带序号的名字（型材材质会拼出假尺寸，如
    角钢1 + 50x50x5 → 150x50x5）。name_base 始终保存不带序号的原始名称。
    """
    by_parent = defaultdict(list)
    for node in nodes:
        by_parent[id(node.parent)].append(node)
    numbered = set()
    for group in by_parent.values():
        counts = Counter(n.row['name'] for n in group)
        seen = defaultdict(int)
        for node in group:
            rid = id(node.row)
            if rid in numbered:
                continue
            numbered.add(rid)
            nm = node.row['name']
            node.row['name_base'] = nm
            if counts[nm] > 1 and not is_std_part(node.row):
                seen[nm] += 1
                node.row['name'] = f'{nm}{seen[nm]}'

def write_total_formula(ws, row, template_last_row):
    """K 列（单台总重）公式：模板自带 =G*J，一律不覆盖（用户规则：不允许改模板格式/公式）。

    只对模板没铺到的行（超出 template_last_row）补写模板同款公式，保持全表一致。
    """
    if row > template_last_row:
        c = ws.cell(row, 11)
        c.value = f'=G{row}*J{row}'
        c.number_format = '0.0000'

def classify_material(r):
    name = r.get('name', '')
    if any(k in name for k in ('钢管', '焊管', '无缝管', '卷管', '钢筒')):
        return 'pipe'
    if '圆钢' in name:
        return 'bar'
    if '钢板' in name or '折弯板' in name or '钢板卷焊' in name:
        return 'plate'
    if any(k in name for k in PROFILE_KEYS):
        return 'profile'
    # 标准件（螺栓/铆钉/销轴等）的规格也常写成“Ø6x10”（直径x长度），
    # 不能按“规格形如 Ødxw 即管材”判定，否则材质列会写成“圆管Ø6x10/316”。
    # 标准件一律走 is_std_part 分支（规格/标准号/强度等级）。
    if is_std_part(r):
        return None
    if re.match(r'^Ø\d+(?:\.\d+)?x\d+(?:\.\d+)?', r.get('spec', '')):
        return 'pipe'
    return None

def plate_thickness(spec):
    # 只从板材尺寸表达式识别厚度，不能把孔径、长度或螺纹数字当板厚。
    s = spec.replace('×', 'x').replace('X', 'x').strip()
    number = r'\d+(?:\.\d+)?'
    explicit = re.search(rf'(?:^|[\s;,；，])(?:t|δ)\s*=?\s*({number})', s, re.I)
    if explicit:
        return f't{float(explicit.group(1)):g}'
    first = re.match(rf'^({number})\s*x', s)
    if first:
        return f't{float(first.group(1)):g}'
    diameter = re.match(rf'^Ø{number}(?:\s*/\s*Ø?{number})?\s*x\s*({number})', s)
    return f't{float(diameter.group(1)):g}' if diameter else None

def spec_no_length(spec):
    return re.sub(r'\s*L\s*[=＝]\s*\d+(?:\.\d+)?\s*(?:mm\b)?', '', spec, flags=re.I).strip()

def base_section_spec(spec, cls):
    """材质列只保留型材/管材的基础截面尺寸，不带长度、孔和加工说明。"""
    s = spec_no_length(spec).strip()
    if not s:
        return ''
    if cls == 'profile':
        # 400x102x12.5x18/26-Ø255 -> 400x102x12.5x18
        return re.split(r'[/（(；;，,]', s, maxsplit=1)[0].strip()
    if cls == 'pipe':
        # DN50 Ø60.3x3.8、Ø42x3.0、Ø256x1 等只保留截面尺寸。
        m = re.match(r'(DN\d+(?:\.\d+)?(?:\s+Ø\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?)?)', s, re.I)
        if m:
            return m.group(1).strip()
        m = re.match(r'(Ø\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?)', s, re.I)
        if m:
            return m.group(1).strip()
        # 钢筒类图纸可能采用 D254-46.5;t=1mm 这种专用截面标注，保留尺寸本身。
        m = re.match(r'(D\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?(?:;\s*t=\d+(?:\.\d+)?mm)?)', s, re.I)
        if m:
            return m.group(1).strip()
        return re.split(r'[/（(；;，,]', s, maxsplit=1)[0].strip()
    if cls == 'bar':
        return re.split(r'[/（(；;，,]', s, maxsplit=1)[0].strip()
    return s

def profile_name(name):
    """型材在材质列只保留通用名称，去掉热轧/冷弯/等边/对称制作等修饰词。"""
    if '空心钢' in name or '方钢' in name:
        return '方管'
    if '槽钢' in name:
        return '槽钢'
    if '角钢' in name:
        return '角钢'
    if 'H型钢' in name:
        return 'H型钢'
    if '工字钢' in name:
        return '工字钢'
    if '扁钢' in name:
        return '扁钢'
    return '型材'

def material_of(r):
    """恢复分类材料表达式；完整尺寸在备注，买方供货不清空。"""
    spec = (r.get('spec') or '').strip()
    material = (r.get('material') or '').strip()
    if refs_of(r):
        return material  # 子图/安装说明不当作原材料规格。
    cls = classify_material(r)
    if material and cls:
        if cls == 'plate':
            thickness = plate_thickness(spec)
            return f'钢板{thickness}/{material}' if thickness else material
        section = spec_no_length(spec)
        if not section:
            return material
        if cls == 'pipe':
            if re.match(r'^\d+(?:\.\d+)?x', section):
                section = 'Ø' + section
            return f'圆管{section}/{material}'
        if cls == 'bar':
            return f'圆棒{section}/{material}'
        if cls == 'profile':
            name = re.sub(r'\d+$', '', r.get('name_base') or r.get('name', ''))
            return f'{name}{section}/{material}'
    if is_std_part(r):
        # 按旧规则保留规格、标准号和强度/表面处理；不凭名称补造标准。
        standard = re.sub(r'图[:：]?|（|）|\(|\)', ' ', r.get('std', ''))
        standard = re.sub(r'\s+', ' ', standard).strip()
        return '/'.join(x for x in (spec, standard, normalize_mat(material)) if x)
    return material

def remark_of(r):
    """供货标记不影响尺寸及加工说明的保留。"""
    return r.get('spec') or ''

# ============================== 高倍率复核 ==============================
VERIFY_COLS_A = {'qty': (240, 310), 'weight': (1310, 1410), 'spec': (560, 960)}
VERIFY_COLS_B = {'qty': (210, 290), 'weight': (1330, 1440), 'spec': (500, 950)}

def norm_cell(cname, t):
    t = (t or '').strip()
    if cname in ('qty', 'weight'):
        m = re.search(r'\d+(?:\.\d+)?', t)
        return m.group(0) if m else ''
    # 规格: 忽略顺序/空格差异, 保留内容差异 —— 比较"数字序列 + 字母符号集合"
    t = t.lower().replace('×', 'x')
    nums = 'N' + '|'.join(sorted(re.findall(r'\d+(?:\.\d+)?', t)))
    chars = 'C' + ''.join(sorted(re.findall(r'[a-zØ]', t)))
    return nums + chars

def verify_cells(pdf_path, doc, cache_dir):
    """对每页的 数量/重量/规格 列做高倍率(scale6)复核。
    返回 (差异列表, 复核单元格总数)"""
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR
    from PIL import Image
    ocr = RapidOCR()
    try:
        pdf = pdfium.PdfDocument(pdf_path)
    except Exception:
        print(f'  [复核跳过] 无法读取PDF(可能被WPS损坏): {os.path.basename(pdf_path)}')
        return [], 0
    diffs, total = [], 0
    for pi, page in enumerate(doc['pages']):
        lines = []
        for it in page:
            box, text, conf = it['box'], it['text'], it['conf']
            xs = [p[0] for p in box]; ys = [p[1] for p in box]
            lines.append(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, min(ys), max(ys),
                          min(xs), max(xs), text, conf))
        header = next((l for l in lines if l[6] == '名称'), None)
        if header is None:
            header = next((l for l in lines if '名称' in l[6]), None)
        if header is None:
            continue
        h_yc = header[1]
        bounds = pick_bounds(lines, h_yc)
        verify_cols = VERIFY_COLS_B if bounds is BOUNDS_B else VERIFY_COLS_A
        h_bottom = h_yc + 30
        data = [l for l in lines if l[1] > h_bottom and l[4] > 60 and not JUNK_RE.search(l[6])]
        data.sort(key=lambda l: l[1])
        bands, cur = [], [data[0]] if data else []
        for l in data[1:]:
            if l[1] - cur[-1][1] < 13.5:
                cur.append(l)
            else:
                bands.append(cur); cur = [l]
        if cur:
            bands.append(cur)
        img6 = pdf[pi].render(scale=6.0).to_pil()
        for band in bands:
            y0 = min(l[2] for l in band) - 6
            y1 = max(l[3] for l in band) + 6
            cells = {}
            for l in band:
                cells.setdefault(col_of(l[0], bounds), []).append(l)
            name = ''
            if 'name' in cells:
                name = ' '.join(l[6] for l in sorted(cells['name'], key=lambda l: l[2]))
            for cname, (x0, x1) in verify_cols.items():
                if cname not in cells:
                    continue
                vals = sorted(cells[cname], key=lambda l: l[2])
                orig = ' '.join(l[6] for l in vals)
                total += 1
                crop = img6.crop((int(x0 * 3), int(y0 * 3), int(x1 * 3), int(y1 * 3)))
                crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
                crop.save('_v.png')
                res, _ = ocr('_v.png')
                high = ''.join(it[1] for it in (res or []))
                orig_norm = norm_cell(cname, orig)
                high_norm = norm_cell(cname, high)
                # 高倍率 OCR 没读出数值不是“冲突”，不能据此把原本清晰的数量/
                # 重量标黄；只有两边都读到数值且不一致时才进入人工复核。
                if cname in ('qty', 'weight') and (not orig_norm or not high_norm):
                    continue
                if orig_norm != high_norm:
                    diffs.append({'page': pi + 1, 'name': name, 'col': cname,
                                  'orig': orig.strip(), 'high': high.strip(),
                                  'row_y': (min(l[1] for l in band) + max(l[1] for l in band)) / 2})
    if os.path.exists('_v.png'):
        os.remove('_v.png')
    return diffs, total

def run_verify(doc_name, pdf_path, doc, cache_dir, report):
    """执行复核并写入报告列表, 返回 (差异数, 复核格数)"""
    diffs, total = verify_cells(pdf_path, doc, cache_dir)
    if diffs:
        report.append(f'--- {os.path.basename(pdf_path)} ({len(diffs)} 处差异 / 复核 {total} 格) ---')
        for d in diffs:
            report.append(f'  第{d["page"]}页 | {d["name"][:22]} | {d["col"]}: 原识别={d["orig"]}  高倍率={d["high"]}')
    return diffs, total

# ============================== 层级与生成 ==============================
class Node:
    __slots__ = ('row', 'children', 'level', 'mult', 'parent', 'number')
    def __init__(self, row=None):
        self.row = row
        self.children = []
        self.level = 0
        self.mult = 1
        self.parent = None
        self.number = ''

def build_tree(main_records, sub_map, root_draw='', root_qty=1):
    root = Node()
    root.mult = root_qty
    # 当前递归链上的图号集合（防循环引用 A→B→C→A 无限递归；同一子图被不同父件
    # 重复引用是合法的，所以不能用全局 visited，只用当前路径）
    active = {root_draw} if root_draw else set()

    def attach(node, records):
        for r in records:
            child = Node(r)
            child.parent = node
            child.level = node.level + 1
            child.mult = safe_product(node.mult, node.row['qty'] if node.row else 1)
            node.children.append(child)
            for ref in refs_of(r):
                if ref in sub_map:
                    if ref in active:
                        print(f'  [警告] 检测到循环引用: {ref}（本分支停止展开）')
                        break
                    active.add(ref)
                    attach(child, sub_map[ref])
                    active.discard(ref)
                    break
    attach(root, main_records)
    return root

def entry_aliases(entry):
    return {entry.get('internal', ''), entry.get('filename', '')} - {''}

def entry_has_material_list(entry):
    """顶层发图登记表/图纸清单类PDF解析不出材料表（无材料表号、0行），不算清单。"""
    return bool(entry['records']) and bool(entry['internal'] or entry['filename'])

def select_root_entries(all_entries, top_pdfs):
    """从顶层PDF中选出没有被其他顶层材料表引用的独立根清单。

    返回 (根清单, 顶层清单, 是否使用全量回退)。顶层清单严格沿用文件名排序，
    使多根合并结果稳定。若循环/自引用导致没有普通根，则保留全部顶层清单，
    绝不能只取第一份而遗漏其余材料表。
    """
    entries_by_path = defaultdict(list)
    for entry in all_entries:
        entries_by_path[os.path.normcase(os.path.abspath(entry['table']['file']))].append(entry)
    top_entries = []
    for path in top_pdfs:
        top_entries.extend(entries_by_path.get(os.path.normcase(os.path.abspath(path)), []))
    referenced = set()
    for entry in top_entries:
        for rec in entry['records']:
            referenced.update(normalize_drawing(x) for x in refs_of(rec))
    roots = [e for e in top_entries if entry_aliases(e).isdisjoint(referenced)]
    fallback_all = not roots and bool(top_entries)
    return (top_entries if fallback_all else roots), top_entries, fallback_all

def node_code(node):
    r = node.row
    own = r['doc_drawing']
    refs = refs_of(r)
    if refs:
        return normalize_drawing(refs[0])  # 明确引用子图时，代号优先采用引用图号
    if not r['part_no']:
        return own          # 件号缺失/格式异常：代号只保留图号（复核报告已标记）
    return f"{own}-{r['part_no']}"

def weight_per(r):
    if r.get('unit_weight') is not None:
        return r['unit_weight']             # 单元格显示4位，内部保留原始精度
    if r['weight'] is None or not r['qty']:
        return None
    return r['weight'] / r['qty']

def safe_product(a, b):
    return None if a is None or b is None else a * b

def detail_weight_total(records):
    """材料表明细重量合计；重量栏是该行数量对应的总重，不再乘数量。"""
    if any(r.get('weight') is None for r in records):
        return None
    weights = [r['weight'] for r in records]
    return round(sum(weights), 4) if weights else None

def numeric_issues(r):
    issues = []
    if r.get('qty_review'):
        issues.append(r['qty_review'])
    if r.get('qty') is None:
        issues.append('数量未识别，留空；不默认填1')
    if r.get('weight') is None and r.get('unit_weight') is None:
        issues.append('重量未识别，需核对原图')
    return issues


def mark_numeric_review(ws, row, node):
    from openpyxl.styles import PatternFill
    from openpyxl.comments import Comment
    r = node.row
    notes = numeric_issues(r)
    columns = set()
    if r.get('qty_review') or r.get('qty') is None:
        columns.update((6, 7, 10, 11))
    if r.get('weight') is None and r.get('unit_weight') is None:
        columns.update((10, 11))
    parent = node.parent
    while parent and parent.row:
        if parent.row.get('qty_review') or parent.row.get('qty') is None:
            notes.append('上级数量待确认，本行单台数量和总重受影响')
            columns.update((7, 11))
            break
        parent = parent.parent
    for col in columns:
        cell = ws.cell(row, col)
        cell.fill = PatternFill('solid', fgColor='FFF2CC')
        cell.comment = Comment('；'.join(notes) + '\n原图：' + r.get('qty_evidence', ''), '工艺清单复核')
    if notes:
        cell = ws.cell(row, 14)
        cell.value = (str(cell.value or '') + '\n【待确认】' + '；'.join(notes)).strip()


# ============================== 缓存键 ==============================
def file_key(pdf_path):
    """按 规范化绝对路径 + 大小 + 修改时间 生成缓存键。
    同名 PDF（兄弟项目）不撞名；PDF 更新过（size/mtime 变化）自动换新键重新 OCR。"""
    st = os.stat(pdf_path)
    ident = f"numeric-review-v3|{os.path.normcase(os.path.abspath(pdf_path))}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.md5(ident.encode('utf-8')).hexdigest()[:12]

def run(source_dir):
    main_pdf, sub_pdfs, top_pdfs = find_project(source_dir)

    # ---- 格式分流：文字型PDF(如瑞士Rowa BOM)走文本提取+翻译路径 ----
    from pdfminer.high_level import extract_text
    try:
        txt = extract_text(main_pdf) or ''
    except Exception:
        txt = ''
    if len(top_pdfs) == 1 and len(txt.strip()) > 200 and not os.path.isdir(os.path.join(source_dir, '分')):
        print('检测到文字型 PDF（Rowa/瑞士格式），走文本提取+翻译路径 ...')
        import swiss_build
        out = swiss_build.build_folder(source_dir)
        if out:
            print(f'\n完成! 输出: {out}')
        return

    print(f'兼容入口PDF: {os.path.basename(main_pdf)}')
    print(f'顶层PDF: {len(top_pdfs)} 个；可展开PDF: {len(sub_pdfs)} 个')

    # 缓存目录（按源文件夹路径哈希，重复运行可跳过OCR）
    key = hashlib.md5(source_dir.encode('utf-8')).hexdigest()[:10]
    cache_dir = os.path.join(DATA_DIR, key)
    os.makedirs(cache_dir, exist_ok=True)

    main_name = 'MAIN_' + file_key(main_pdf)
    main_doc = None
    main_json = os.path.join(cache_dir, main_name + '.json')
    if os.path.exists(main_json):
        with open(main_json, encoding='utf-8') as f:
            main_doc = json.load(f)
        print('(使用已缓存的OCR结果)')
    else:
        main_doc = do_ocr(main_pdf, cache_dir, main_name)
    if main_doc is None:
        print(f'\n错误: 主清单PDF无法读取（可能被WPS损坏）: {os.path.basename(main_pdf)}')
        print('请重新获取这份PDF（不要用WPS打开保存它）后再运行。')
        sys.exit(1)
    docs = {main_name: main_doc}

    # 本项目“分”目录全部保留；兄弟项目只按主表/已加载子表中的实际引用递归加载。
    # 这样仍支持跨项目引用，但不会把同级所有项目混进 OCR 和复核报告。
    source_abs = os.path.normcase(os.path.abspath(source_dir))
    def is_local_pdf(path):
        try:
            return os.path.commonpath([source_abs, os.path.normcase(os.path.abspath(path))]) == source_abs
        except ValueError:
            return False
    wanted = {normalize_drawing(x) for x in DRAW_RE.findall(
        '\n'.join(it['text'] for page in main_doc.get('pages', []) for it in page))}
    # 合订 PDF 自身已经包含的材料表可直接用于展开，不再去兄弟项目重复加载
    # 同图号 PDF。既能明显减少 OCR 时间，也避免旧版兄弟文件覆盖合订本内容。
    embedded_tables = build_tables(cache_dir, only_names={main_name})
    embedded_drawings = {
        normalize_drawing(t['meta'].get('drawing', ''))
        for t in embedded_tables.values() if t['meta'].get('drawing')
    }
    wanted.difference_update(embedded_drawings)
    pending = [(d, p) for d, p in sub_pdfs.items() if is_local_pdf(p) or normalize_drawing(d) in wanted]
    loaded_paths = set()
    pos = 0
    while pos < len(pending):
        d, p = pending[pos]
        pos += 1
        path_key = os.path.normcase(os.path.abspath(p))
        if path_key in loaded_paths:
            continue
        loaded_paths.add(path_key)
        sub_name = 'SUB_' + file_key(p)
        sj = os.path.join(cache_dir, sub_name + '.json')
        if os.path.exists(sj):
            with open(sj, encoding='utf-8') as f:
                docs[sub_name] = json.load(f)
            print(f'(使用已缓存的OCR结果: {os.path.basename(p)})')
        else:
            sub_doc = do_ocr(p, cache_dir, sub_name)
            if sub_doc is None:
                continue  # 子件PDF损坏则跳过（对应图号不展开）
            docs[sub_name] = sub_doc
        doc_now = docs.get(sub_name, {})
        new_refs = {normalize_drawing(x) for x in DRAW_RE.findall(
            '\n'.join(it['text'] for page in doc_now.get('pages', []) for it in page))}
        wanted.update(new_refs)
        queued = {os.path.normcase(os.path.abspath(x[1])) for x in pending}
        for ref in new_refs:
            ext = sub_pdfs.get(ref)
            if ext and os.path.normcase(os.path.abspath(ext)) not in queued | loaded_paths:
                pending.append((ref, ext))

    # 只读取本次实际扫描到的缓存（防止已删除子件的旧缓存污染结果）
    tables = build_tables(cache_dir, only_names=set(docs.keys()))
    # ---- 高倍率复读：可靠结果直接回写，复核报告保留变更轨迹 ----
    reread_missing_part_numbers(tables)
    reread_missing_weights(tables)
    reread_quantities(tables, os.path.join(source_dir, '数量复核原图'))

    # ---- 子清单页脚总重捕获（低倍率缺失时 scale6 复读）----
    extra_totals = capture_total_weights(tables)

    # ---- 高倍率复核：数量/重量/规格 列（图片型OCR路径自动执行）----
    print('\n正在做高倍率复核（数量/重量/规格列）...')
    report = ['高倍率复核报告（数量/重量/规格列）', '=' * 60]
    n_diff = n_total = 0
    verified_sources = set()
    for sub_name, t in tables.items():
        source_name = t.get('source_name', sub_name)
        if source_name in verified_sources:
            continue
        verified_sources.add(source_name)
        doc = docs.get(source_name)
        if doc is None or (source_name != main_name and not is_local_pdf(t['file'])):
            continue
        source_tables = [candidate for candidate in tables.values()
                         if candidate.get('source_name', source_name) == source_name]
        d, tot = run_verify(sub_name, doc['file'], doc, cache_dir, report)
        for diff in d:
            if diff['col'] != 'qty':
                continue
            matches = [rec for candidate in source_tables for rec in candidate['records']
                       if rec.get('_page', 0) == diff['page'] - 1
                       and abs(rec.get('_y', -999) - diff['row_y']) < 7]
            if len(matches) == 1:
                matches[0]['_qty_review'] = (f"数量复核冲突：原识别={diff['orig']}，高倍率={diff['high']}；需核对原图")
        n_diff += len(d)
        n_total += tot
    print(f'复核完成: 共 {n_total} 格, 发现 {n_diff} 处与原识别不一致')
    rp = os.path.join(source_dir, '复核报告.txt')

    # 所有实际加载的PDF（包括兼容入口PDF）同时按“PDF内部材料表号”和
    # “文件名图号”建立别名。这样第一份PDF即使恰好是子清单，也仍能被
    # 其他顶层根清单正确引用和展开。
    sub_map = {}
    all_entries = []
    drawing_alias_issues = []
    top_path_keys = {os.path.normcase(os.path.abspath(p)) for p in top_pdfs}
    for sub_name, t in tables.items():
        internal = normalize_drawing(t['meta'].get('drawing', ''))
        filename_raw = normalize_drawing(drawing_from_filename(os.path.basename(t['file'])))
        filename_draw = filename_raw if DRAW_RE.fullmatch(filename_raw) else ''
        recs = process_doc(t)
        # 文件名/父表引用与PDF内部材料表号冲突时，输出采用文件名/引用图号；
        # 内部号仍记录在复核报告中，不能静默忽略。
        if internal and filename_draw and internal != filename_draw:
            for rec in recs:
                rec['doc_drawing'] = filename_draw
        entry = {'name': sub_name, 'table': t, 'records': recs,
                 'internal': internal, 'filename': filename_draw}
        all_entries.append(entry)
        is_top_entry = os.path.normcase(os.path.abspath(t['file'])) in top_path_keys
        if internal:
            if is_top_entry:
                sub_map[internal] = recs
            else:
                sub_map.setdefault(internal, recs)
        if filename_draw:
            if is_top_entry:
                sub_map[filename_draw] = recs
            else:
                sub_map.setdefault(filename_draw, recs)
        if internal and filename_draw and internal != filename_draw:
            drawing_alias_issues.append((os.path.basename(t['file']), filename_draw, internal))

    root_entries, top_entries, root_fallback = select_root_entries(all_entries, top_pdfs)

    def has_material_list(entry):
        return entry_has_material_list(entry)

    roots_from_subfolder = False
    if not any(has_material_list(e) for e in top_entries) and len(all_entries) > len(top_entries):
        # 本文件夹没有顶层总清单（例如只放了发图登记表，材料表全在 分\ 子文件夹里）。
        # 按全局引用关系从所有实际材料表里选根：没有被子图引用的材料表即独立根，
        # 引用关系仍由 sub_map 展开，输出合并为一份总清单。
        valid = [e for e in all_entries if has_material_list(e)]
        referenced = set()
        for e in valid:
            for rec in e['records']:
                referenced.update(normalize_drawing(x) for x in refs_of(rec))
        roots = [e for e in valid if entry_aliases(e).isdisjoint(referenced)]
        # 缓存文件名是路径哈希，遍历顺序不确定；多根合并必须按图号排序，输出才稳定。
        roots.sort(key=lambda e: draw_sort_key(e['internal'] or e['filename']))
        root_entries, root_fallback = (roots or valid), False
        roots_from_subfolder = True
        report.append('\n--- 无顶层总清单：按引用关系合并 分\\ 内的独立材料表 ---')
        report.append('  顶层PDF没有材料表（发图登记表/图纸清单不是材料表），已改按引用关系'
                      f'从 分\\ 内的材料表中选出 {len(root_entries)} 个根清单（明细见下）。')

    if root_fallback:
        report.append('\n--- 根清单识别回退（需人工确认）---')
        report.append('  未找到未被引用的顶层PDF（可能存在循环/自引用），已合并全部可读顶层PDF，未丢弃任何一份。')
    elif not root_entries:
        # 理论上主PDF可读时不会进入；仍以全量而非首份兜底，避免静默遗漏。
        root_entries = list(all_entries)
        report.append('\n--- 根清单识别回退（需人工确认）---')
        report.append('  顶层PDF未能建立条目，已合并全部可读材料表，未丢弃任何一份。')
    if len(root_entries) > 1:
        report.append('\n--- 多根清单合并 ---')
        for entry in root_entries:
            report.append(f"  {entry['internal'] or entry['filename']} | {entry['table']['meta'].get('name', '')}")

    # 件号异常（缺失/格式不符）追加到复核报告：不重编号，只标记
    part_issues = []
    name_issues = []
    for entry in all_entries:
        d, recs = entry['internal'] or entry['filename'], entry['records']
        part_issues += [(d, r['name'], r.get('seq_raw', '')) for r in recs if not r['part_no']]
        name_issues += [(d, r.get('part_no') or r.get('seq_raw', '')) for r in recs if not r['name']]

    # ---- 子清单重量优先：独立材料表页脚总重覆盖总清单对应部件重量 ----
    sub_weight_map = {}
    sub_info_map = {}
    computed_totals = []
    detail_total_issues = []
    for entry in all_entries:
        sub_name, t, recs = entry['name'], entry['table'], entry['records']
        tw = t.get('total_weight')
        if tw is None:
            tw = extra_totals.get(sub_name)
        if tw is None:
            tw = detail_weight_total(recs)
            if tw is not None:
                computed_totals.append((entry['internal'] or entry['filename'], tw))
        else:
            detail_total = detail_weight_total(recs)
            if detail_total is not None and abs(detail_total - tw) > 0.005:
                detail_total_issues.append(
                    (entry['internal'] or entry['filename'], detail_total, tw))
        meta_qty = parse_int(str(t['meta'].get('qty', '')))
        info = {'weight': tw, 'meta_qty': meta_qty, 'entry': entry,
                'complete': detail_weight_total(recs) is not None}
        for alias in {entry['internal'], entry['filename']} - {''}:
            sub_info_map[alias] = info
            if tw is not None:
                sub_weight_map[alias] = tw

    # 通过“父表总重 ≈ 子表单件总重 × 制造数量”校验并修复父件数量。
    qty_repairs = []
    def repair_parent_qty(records):
        for r in records:
            for ref in refs_of(r):
                refn = normalize_drawing(ref)
                info = sub_info_map.get(refn)
                if (not info or not info['weight'] or not info['complete']
                        or r['weight'] is None or r.get('qty_review') or r['qty'] is None):
                    continue
                unit_w = info['weight']
                ratio = r['weight'] / unit_w
                inferred = int(round(ratio))
                target = info['meta_qty'] if info['meta_qty'] else inferred
                tolerance = max(0.06, abs(unit_w * target) * 0.02)
                if target >= 1 and abs(r['weight'] - unit_w * target) <= tolerance and r['qty'] != target:
                    old = r['qty']
                    r['qty'] = target
                    qty_repairs.append((r['doc_drawing'], r['name'], old, target, refn))
                break
    for entry in all_entries:
        repair_parent_qty(entry['records'])

    overrides = []
    missing_totals = set()
    def override_weight(records):
        for r in records:
            for ref in refs_of(r):
                refn = normalize_drawing(ref)
                if refn in sub_weight_map:
                    r['weight_original'] = r['weight']
                    sub_unit = sub_weight_map[refn]
                    # 父表重量是该行全部数量的总重。与子表总重基本一致时，
                    # 用“父表总重÷数量”的完整精度作为单件重量，保证再乘后
                    # 精确回到父表原值；子表总重继续用于校验和缺失兜底。
                    main_unit = (r['weight'] / r['qty']) if r['weight'] is not None and r['qty'] else None
                    tolerance = max(0.06, abs(sub_unit) * 0.02)
                    if main_unit is not None and abs(main_unit - sub_unit) <= tolerance:
                        r['unit_weight'] = main_unit
                        r['weight_source'] = 'main_total_per_qty'
                    else:
                        r['unit_weight'] = sub_unit
                        r['weight_source'] = 'sub_pdf'
                    overrides.append((r['doc_drawing'], r['name'], r['weight_original'], r['unit_weight']))
                    break
                if refn in sub_map and refn not in missing_totals:
                    missing_totals.add(refn)   # 引用了子图但没捕获到子图总重
    for entry in all_entries:
        override_weight(entry['records'])

    # 把自动修正和仍需人工确认的内容统一写入报告。
    if drawing_alias_issues:
        report.append('\n--- 图号别名匹配（文件名与PDF内部材料表号不一致）---')
        for fn, alias, internal in drawing_alias_issues:
            report.append(f'  {fn} | 文件名={alias} | 内部材料表号={internal}（已按别名展开）')
    reread_changes = []
    seq_reread_changes = []
    for t in tables.values():
        for rec in t['records']:
            if '_qty_original' in rec:
                reread_changes.append((os.path.basename(t['file']), rec.get('name', ('', 0))[0],
                                       rec['_qty_original'], rec.get('qty', ('', 0))[0]))
            if '_seq_original' in rec:
                seq_reread_changes.append((os.path.basename(t['file']), rec.get('name', ('', 0))[0],
                                           rec['_seq_original'], rec.get('seq', ('', 0))[0]))
    if seq_reread_changes:
        report.append('\n--- 件号自动修正（高倍率复读）---')
        for fn, name, old, new in seq_reread_changes:
            report.append(f'  {fn} | {name} | {old} → {new}')
    if reread_changes or qty_repairs:
        report.append('\n--- 数量自动修正 ---')
        for fn, name, old, new in reread_changes:
            report.append(f'  {fn} | {name} | {old} → {new}（高倍率复读）')
        for d, name, old, new, ref in qty_repairs:
            report.append(f'  {d} | {name} | {old} → {new}（与子表 {ref} 总重/制造数量一致）')
    if computed_totals:
        report.append('\n--- 子清单总重回退计算（页脚未识别，按明细重量合计）---')
        for d, tw in computed_totals:
            report.append(f'  {d} | 合计={tw}')
    if detail_total_issues:
        report.append('\n--- PDF明细重量合计与页脚总重不一致（源表矛盾，未擅自改数）---')
        for d, detail_total, footer_total in detail_total_issues:
            report.append(f'  {d} | 明细合计={detail_total:.2f} | 页脚总重={footer_total:.2f}')
    if overrides:
        report.append('\n--- 装配件重量校验（父表总重保持精度，子表总重用于核对/兜底）---')
        for d, name, orig, new in overrides:
            report.append(f'  {d} | {name} | 总清单={orig} → 独立清单单件={new}')
    if missing_totals:
        report.append('\n--- 子清单总重未捕获（保持总清单重量，需人工核对）---')
        for d in sorted(missing_totals):
            report.append(f'  {d}')
    if part_issues:
        report.append('\n--- 件号复核（缺失/格式异常，代号只保留图号，需人工补件号）---')
        for d, name, raw in part_issues:
            report.append(f'  {d} | {name or "<名称空白>"} | OCR件号={raw!r}')
    if name_issues:
        report.append('\n--- 名称复核（PDF名称栏为空白或未识别，不自动猜测）---')
        for d, part in name_issues:
            report.append(f'  {d}-{part} | 名称为空白')
    report.append('\n--- 数量及重量待确认（Excel 黄色单元格）---')
    for entry in all_entries:
        for r in entry['records']:
            issues = numeric_issues(r)
            if issues:
                report.append(f"  {r['doc_drawing']} | {r['name']} | {'；'.join(issues)} | 原图={r.get('qty_evidence', '')}")
    with open(rp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    print(f'复核报告已保存: {rp}')

    # 层级序号严格使用 PDF 原件号，保留跳号和 2.1 等原始层级，不连续重编。
    def assign_numbers(parent):
        for c in parent.children:
            part = c.row.get('part_no') or '?'
            c.number = (parent.number + '.' if parent.number else '') + part
            assign_numbers(c)
    flat = []
    root_context = {}
    def flatten(node):
        if node.row:
            flat.append(node)
        for c in node.children:
            flatten(c)

    for root_index, entry in enumerate(root_entries, start=1):
        root_draw = entry['internal'] or entry['filename']
        root_name = entry['table']['meta'].get('name', '')
        root_info = sub_info_map.get(root_draw, {})
        root_qty = root_info.get('meta_qty') or 1
        root_weight = root_info.get('weight')
        root = build_tree(entry['records'], sub_map, root_draw, root_qty)
        root.number = str(root_index)
        assign_numbers(root)
        before = len(flat)
        heading = Node({
            'seq': None, 'seq_raw': '', 'part_no': None,
            'qty': root_qty, 'unit': '件', 'name': root_name,
            'spec': '', 'std': '', 'material': '',
            'weight': None, 'unit_weight': root_weight,
            'supplier': '', 'cat': '', 'doc_drawing': root_draw,
            'ares': False, 'qty_review': '', 'qty_evidence': '',
            '_root_heading': True,
        })
        heading.number = str(root_index)
        flat.append(heading)
        flatten(root)
        for node in flat[before:]:
            root_context[id(node)] = (root_draw, root_name)

    # 同一父件下重名子件在名称后加序号（标准件除外）——用户规则第7条。
    # PDF 原文名称保存在 name_base，材质列（型材）取 name_base，避免序号粘到尺寸上。
    number_duplicate_names(flat)

    root_contracts = list(dict.fromkeys(
        entry['table']['meta'].get('contract', '') for entry in root_entries
        if entry['table']['meta'].get('contract', '')
    ))
    root_contract = '/'.join(root_contracts)
    if len(root_entries) == 1:
        output_root_name = root_entries[0]['table']['meta'].get('name', '')
        output_root_draw = root_entries[0]['internal'] or root_entries[0]['filename']
        title = f"{root_contract} {output_root_name}（{output_root_draw}）"
        out_name = f"工艺清单_{output_root_name}（{output_root_draw}）.xlsx"
    else:
        root_files = {os.path.normcase(os.path.abspath(e['table']['file'])) for e in root_entries}
        if len(root_files) == 1 and len(top_pdfs) == 1:
            # 单个合订 PDF 内含多张独立材料表：沿用源 PDF 名覆盖旧输出，
            # 避免在同一文件夹里同时留下“旧清单”和“总清单”两个版本。
            pdf_name = os.path.basename(top_pdfs[0])
            source_label = os.path.splitext(pdf_name)[0]
            title = f"{root_contract} {source_label}（总清单）"
            out_name = f"工艺清单_（{pdf_name}）.xlsx"
        else:
            folder_name = os.path.basename(os.path.normpath(source_dir))
            # 项目文件夹名常带交付日期（如“300炉顶导风板（2026.9.14）”），
            # 输出文件名里去掉这层日期，保留设备/项目名。
            folder_label = re.sub(r'[（(]\s*\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\s*[)）]\s*$',
                                  '', folder_name).strip() or folder_name
            title = f"{root_contract} {folder_label}（总清单）"
            out_name = f"工艺清单_{folder_label}（总清单）.xlsx"

    def parent_ref(node):
        if node.row.get('_root_heading'):
            return ('', '')
        p = node.parent
        if p is None or p.row is None:
            return root_context[id(node)]
        return (node_code(p), p.row['name'])

    # 生成 Excel
    import openpyxl
    from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
    wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb['模板表单']
    ws['C1'] = title

    thin = Side(style='thin', color='000000')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    FONT = Font(name='宋体', size=12)
    FONT_B = Font(name='宋体', size=12, bold=True)
    ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)

    r0 = 3
    # 模板已铺好格式和公式的末行：模板范围内的单元格（数字格式、公式）一律不动，
    # 只有超出这个范围的行才由程序补写（用户规则：不允许修改任何清单模板格式）。
    template_last_row = ws.max_row
    row_of = {id(node): r0 + i for i, node in enumerate(flat)}
    for i, node in enumerate(flat):
        r = node.row
        xr = r0 + i
        ws.row_dimensions[xr].height = 26      # 数据行行高固定26磅（第1、2行保持模板）
        pref, pname = parent_ref(node)
        data = {
            1: node.number,
            2: node_code(node),
            3: r['name'],
            4: pref,
            5: pname,
            6: r['qty'],
            7: safe_product(r['qty'], node.mult),
            9: material_of(r),
            10: weight_per(r),
            14: remark_of(r),
        }
        bold = bool(node.children or r.get('_root_heading'))
        for ci in range(1, 20):
            c = ws.cell(xr, ci)
            c.font = FONT_B if bold else FONT
            c.border = border
            c.alignment = ALIGN
            if ci in data:
                c.value = data[ci]
            if xr > template_last_row:
                if ci in (6, 7):
                    c.number_format = '0.###'
                elif ci in (10, 11):
                    c.number_format = '0.0000'
        # K 列（单台总重）= 单台数量 × 单件重量：模板公式不动，只补模板没铺到的行
        write_total_formula(ws, xr, template_last_row)
    for xr in range(3, ws.max_row + 1):
        for ci in range(1, 20):
            c = ws.cell(xr, ci)
            if c.fill and c.fill.patternType:
                c.fill = PatternFill()

    for i, node in enumerate(flat):
        mark_numeric_review(ws, r0 + i, node)

    out_path = os.path.join(source_dir, out_name)
    try:
        wb.save(out_path)
        print(f'\n完成! 合并根清单 {len(root_entries)} 个，共 {len(flat)} 行')
        if roots_from_subfolder:
            print(f'（本文件夹没有顶层总清单，根清单取自 分\\ 子文件夹的 {len(root_entries)} 份独立材料表）')
        print(f'输出: {out_path}')
    except PermissionError:
        alt = os.path.join(source_dir, out_name[:-5] + '（新）.xlsx')
        wb.save(alt)
        print(f'\n注意: 目标文件正被占用(可能WPS打开)，已另存为:\n  {alt}')
        print(f'完成! 共 {len(flat)} 行')

    # 打印前几行供核对
    for node in flat[:8]:
        r = node.row
        print(f"  {node.number:<6}{r['name']:<20} 数量{safe_product(node.mult, r['qty'])}  材质:{material_of(r)}")

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else input('请输入图纸材料表PDF所在文件夹路径：').strip().strip('"')
    if not src:
        print('未输入路径')
        sys.exit(1)
    run(src)
