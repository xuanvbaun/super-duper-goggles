# -*- coding: utf-8 -*-
"""没有顶层总清单（例如只放了发图登记表）时的根清单选择，以及本批确认的分类/件号修正。"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


PROGRAM = Path(__file__).resolve().parents[1] / "run.py"
spec = importlib.util.spec_from_file_location("craft_run2", PROGRAM)
craft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(craft)


def record(drawing, part, name, std="", qty=1, material="", spec="", cat=""):
    return {
        "doc_drawing": drawing, "part_no": str(part), "name": name, "std": std,
        "qty": qty, "material": material, "spec": spec, "cat": cat, "ares": False,
    }


def entry(path, drawing, records=(), name=""):
    return {
        "table": {"file": path, "meta": {"drawing": drawing, "name": name or drawing}},
        "internal": drawing, "filename": drawing, "records": list(records),
    }


class RegistryFileTests(unittest.TestCase):
    def test_registry_pdf_is_not_used_as_main_when_list_pdf_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "发图登记表(1).pdf").touch()
            Path(folder, "GDL161-300-01-A炉体钢结构（图纸材料表）.pdf").touch()
            main, _, top = craft.find_project(folder)
            self.assertEqual(len(top), 2)
            self.assertIn("图纸材料表", os.path.basename(main))

    def test_registry_pdf_stays_usable_when_it_is_the_only_top_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "发图登记表.pdf").touch()
            Path(folder, "分").mkdir()
            main, _, top = craft.find_project(folder)
            self.assertEqual(len(top), 1)
            self.assertTrue(os.path.basename(main).startswith("发图登记表"))


class HasMaterialListTests(unittest.TestCase):
    def test_registry_entry_has_no_material_list(self):
        registry = entry("发图登记表.pdf", "")
        self.assertFalse(craft.entry_has_material_list(registry))

    def test_real_material_table_is_a_list(self):
        real = entry("分/GDL161-300-09-A.pdf", "GDL161-300-09",
                     [record("GDL161-300-09", 1, "风机下导风板")])
        self.assertTrue(craft.entry_has_material_list(real))


class RootSortTests(unittest.TestCase):
    def test_drawing_sort_key_is_natural(self):
        codes = ["GDL161-300-32", "GDL161-300-09", "GDL161-300-18", "GDL161-300-100"]
        self.assertEqual(sorted(codes, key=craft.draw_sort_key),
                         ["GDL161-300-09", "GDL161-300-18", "GDL161-300-32", "GDL161-300-100"])

    def test_subfolder_roots_skip_referenced_drawings(self):
        """分 内的独立材料表按引用关系选根：被别的材料表引用的不是根。"""
        assembly = entry("分/09.pdf", "GDL161-300-09",
                         [record("GDL161-300-09", 1, "风机下导风板", "图：GDL161-300-12")])
        child = entry("分/12.pdf", "GDL161-300-12", [record("GDL161-300-12", 1, "冷弯方形空心钢")])
        standalone = entry("分/32.pdf", "GDL161-300-32", [record("GDL161-300-32", 1, "热轧钢板")])
        valid = [assembly, child, standalone]
        referenced = {craft.normalize_drawing(x) for e in valid for r in e["records"] for x in craft.refs_of(r)}
        roots = [e for e in valid if craft.entry_aliases(e).isdisjoint(referenced)]
        roots.sort(key=lambda e: craft.draw_sort_key(e["internal"] or e["filename"]))
        self.assertEqual([e["internal"] for e in roots], ["GDL161-300-09", "GDL161-300-32"])


class StandardPartMaterialTests(unittest.TestCase):
    def test_rivet_with_diameter_spec_is_not_treated_as_pipe(self):
        row = {"ares": False, "name": "316不锈钢圆头铆钉", "spec": "Ø6x10",
               "material": "316", "std": "", "cat": "16"}
        self.assertIsNone(craft.classify_material(row))
        self.assertEqual(craft.material_of(row), "Ø6x10/316")

    def test_pipe_with_diameter_spec_is_still_pipe(self):
        row = {"ares": False, "name": "输送管", "spec": "Ø57x3.5 L=200", "material": "0Cr18Ni9"}
        self.assertEqual(craft.classify_material(row), "pipe")
        self.assertEqual(craft.material_of(row), "圆管Ø57x3.5/0Cr18Ni9")


class SeqRawCorrectionTests(unittest.TestCase):
    def test_seq_raw_eq_only_fires_on_the_wrong_reading(self):
        corrections = [{"id": "t", "drawing": "GDL161-300-10", "name": "炉顶和侧墙拉杆1",
                        "seq_raw_eq": "9", "set": {"seq_raw": "6"}}]
        wrong = {"doc_drawing": "GDL161-300-10", "name": "炉顶和侧墙拉杆1", "seq_raw": "9",
                 "spec": "", "qty": 12, "material": "", "weight": 10.44, "cat": "24"}
        right = dict(wrong, seq_raw="6")
        craft.apply_corrections([wrong, right], corrections)
        self.assertEqual(wrong["seq_raw"], "6")
        self.assertEqual(right["seq_raw"], "6")   # 将来 OCR 读对时不会被改坏

    def test_confirmed_corrections_for_this_batch_are_present(self):
        ids = {c["id"] for c in craft.CORRECTIONS}
        self.assertIn("gdl161-300-10-lagan1-partno", ids)
        self.assertIn("gdl161-300-20-plate6-partno", ids)
        self.assertIn("gdl161-300-31-tube-qty-confirm", ids)


class CleanSpecTests(unittest.TestCase):
    def test_space_inside_chinese_text_is_removed(self):
        self.assertEqual(craft.clean_spec("一端制作G1-1/4\"外螺 纹，螺纹长度30mm"),
                         "一端制作G1-1/4\"外螺纹，螺纹长度30mm")


if __name__ == "__main__":
    unittest.main()
