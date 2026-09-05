import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


PROGRAM = Path(__file__).resolve().parents[1] / "run.py"
spec = importlib.util.spec_from_file_location("craft_run", PROGRAM)
craft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(craft)


def record(drawing, part, name, std="", qty=1, material=""):
    return {
        "doc_drawing": drawing,
        "part_no": str(part),
        "name": name,
        "std": std,
        "qty": qty,
        "material": material,
        "ares": False,
    }


def entry(path, drawing, records):
    return {
        "table": {"file": path, "meta": {"drawing": drawing, "name": drawing}},
        "internal": drawing,
        "filename": drawing,
        "records": records,
    }


class MultiRootTests(unittest.TestCase):
    def test_find_project_keeps_every_top_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            names = ["GDL157-450-05-A.pdf", "GDL161-450-01-A.pdf", "GDL161-450-02-A.pdf"]
            for name in names:
                Path(folder, name).touch()
            main, candidates, top = craft.find_project(folder)
            self.assertEqual(len(top), 3)
            self.assertEqual(len(candidates), 2)
            self.assertTrue(main.endswith(names[0]))

    def test_two_independent_roots_are_both_selected(self):
        paths = [os.path.abspath("root-a.pdf"), os.path.abspath("root-b.pdf")]
        entries = [entry(paths[0], "GDL161-450-01", []), entry(paths[1], "GDL161-450-02", [])]
        roots, _, fallback = craft.select_root_entries(entries, paths)
        self.assertEqual([e["internal"] for e in roots], ["GDL161-450-01", "GDL161-450-02"])
        self.assertFalse(fallback)

    def test_referenced_top_pdf_is_child_not_root(self):
        paths = [os.path.abspath("root.pdf"), os.path.abspath("child.pdf")]
        entries = [
            entry(paths[0], "GDL161-450-01", [record("GDL161-450-01", 5, "法兰", "图：GDL157-450-05")]),
            entry(paths[1], "GDL157-450-05", []),
        ]
        roots, _, fallback = craft.select_root_entries(entries, paths)
        self.assertEqual([e["internal"] for e in roots], ["GDL161-450-01"])
        self.assertFalse(fallback)

    def test_root_order_follows_top_pdf_order(self):
        paths = [os.path.abspath("root-a.pdf"), os.path.abspath("root-b.pdf")]
        entries = [entry(paths[1], "GDL161-450-02", []), entry(paths[0], "GDL161-450-01", [])]
        roots, _, _ = craft.select_root_entries(entries, paths)
        self.assertEqual([e["internal"] for e in roots], ["GDL161-450-01", "GDL161-450-02"])

    def test_cyclic_top_references_keep_every_pdf(self):
        paths = [os.path.abspath("root-a.pdf"), os.path.abspath("root-b.pdf")]
        entries = [
            entry(paths[0], "GDL161-450-01", [record("GDL161-450-01", 1, "B装配", "图：GDL161-450-02")]),
            entry(paths[1], "GDL161-450-02", [record("GDL161-450-02", 1, "A装配", "图：GDL161-450-01")]),
        ]
        roots, _, fallback = craft.select_root_entries(entries, paths)
        self.assertEqual([e["internal"] for e in roots], ["GDL161-450-01", "GDL161-450-02"])
        self.assertTrue(fallback)

    def test_tree_expands_referenced_child(self):
        parent = record("GDL161-450-01", 5, "烧嘴安装法兰", "图：GDL157-450-05")
        child = record("GDL157-450-05", 1, "法兰")
        tree = craft.build_tree([parent], {"GDL157-450-05": [child]}, "GDL161-450-01")
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].children[0].row["name"], "法兰")

    def test_fractional_quantity_is_preserved(self):
        self.assertEqual(craft._clean_qty("0.615 米"), 0.615)
        self.assertEqual(craft._clean_qty("6件"), 6)

    def test_ares_material_code_is_not_discarded(self):
        self.assertEqual(craft.material_of({"ares": True, "material": "A10.06.164-2500"}),
                         "A10.06.164-2500")

    def test_standard_part_material_does_not_absorb_spec_or_standard(self):
        row = {"ares": False, "material": "钢8.8", "name": "内六角凹端螺钉",
               "spec": "M16x60", "std": "GB/T80-2007", "cat": "16"}
        self.assertEqual(craft.material_of(row), "钢8.8")

    def test_weight_is_recovered_from_merged_supplier_cell(self):
        table = {
            "meta": {"drawing": "GDL161-450-01-A"},
            "records": [
                {"seq": ("2", 1), "qty": ("1", 1), "unit": ("件", 1),
                 "name": ("陶瓷辐射管", 1), "material": ("A10.06.164-2500", 1),
                 "supplier": ("23.21 Ares", 1)},
            ],
        }
        row = craft.process_doc(table)[0]
        self.assertEqual(row["weight"], 23.21)
        self.assertEqual(row["supplier"], "Ares")
        self.assertTrue(row["ares"])

    def test_detail_weight_total_does_not_multiply_quantity_twice(self):
        rows = [{"qty": 2, "weight": 7.55}, {"qty": 1, "weight": 1.27},
                {"qty": 1, "weight": None}]
        self.assertEqual(craft.detail_weight_total(rows), 8.82)

    def test_confirmed_m120_flange_ocr_errors_are_corrected(self):
        table = {
            "meta": {"drawing": "GDL157-450-06-A"},
            "records": [
                {"seq": ("4 2", 1), "qty": ("3", 1), "unit": ("件", 1),
                 "spec": ("Ø370/Ø194×22", 1), "material": ("2Cr13", 1),
                 "weight": ("10.89", 1)},
                {"seq": ("4 2", 1), "qty": ("8", 1), "unit": ("件", 1),
                 "name": ("内六角凹端螺钉", 1), "spec": ("M16x60", 1),
                 "std": ("GB/T80-2007", 1), "material": ("钢8.8", 1),
                 "weight": ("0.40", 1)},
            ],
        }
        rows = craft.process_doc(table)
        self.assertEqual((rows[0]["part_no"], rows[0]["qty"], rows[0]["name"]),
                         ("1", 1, "法兰"))
        self.assertEqual((rows[1]["part_no"], rows[1]["qty"]), ("2", 4))


if __name__ == "__main__":
    unittest.main()
