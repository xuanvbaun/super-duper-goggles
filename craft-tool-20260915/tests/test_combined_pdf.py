import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "combined_craft", Path(__file__).resolve().parents[1] / "run.py"
)
craft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(craft)


def parsed_row(seq, name):
    return {
        "y": 100,
        "cols": {
            "seq": [(seq, 0.99, 90)],
            "qty": [("1", 0.99, 90)],
            "name": [(name, 0.99, 90)],
        },
    }


class CombinedPdfTests(unittest.TestCase):
    def test_one_pdf_is_split_into_independent_material_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            doc = {"file": str(cache / "combined.pdf"), "pages": [[], [], []]}
            (cache / "MAIN.json").write_text(json.dumps(doc), encoding="utf-8")

            def page_meta(_doc, page_index=0):
                return ({},
                        {"drawing": "GDL161-300-09", "name": "装配一"},
                        {"drawing": "GDL161-300-10", "name": "装配二"})[page_index]

            with patch.object(craft, "parse_page",
                              side_effect=[None, [parsed_row("1", "件一")], [parsed_row("1", "件二")]]), \
                 patch.object(craft, "meta_of", side_effect=page_meta):
                tables = craft.build_tables(str(cache), only_names={"MAIN"})

        self.assertEqual(set(tables), {"MAIN__P002", "MAIN__P003"})
        self.assertEqual(tables["MAIN__P002"]["meta"]["drawing"], "GDL161-300-09")
        self.assertEqual(tables["MAIN__P003"]["meta"]["drawing"], "GDL161-300-10")
        self.assertEqual(tables["MAIN__P002"]["source_pages"], [1])
        self.assertEqual(tables["MAIN__P003"]["source_pages"], [2])

    def test_all_tables_from_same_top_pdf_participate_in_root_selection(self):
        path = str(Path("combined.pdf").resolve())
        entries = [
            {"table": {"file": path}, "records": [], "internal": "GDL161-300-09", "filename": ""},
            {"table": {"file": path}, "records": [], "internal": "GDL161-300-10", "filename": ""},
        ]
        roots, top, fallback = craft.select_root_entries(entries, [path])
        self.assertEqual(len(top), 2)
        self.assertEqual(len(roots), 2)
        self.assertFalse(fallback)

    def test_changed_equipment_name_splits_page_when_drawing_number_is_missed(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            doc = {"file": str(cache / "combined.pdf"), "pages": [[], []]}
            (cache / "MAIN.json").write_text(json.dumps(doc), encoding="utf-8")

            def page_meta(_doc, page_index=0):
                return ({"drawing": "GDL161-300-09", "name": "装配一"},
                        {"name": "装配二"})[page_index]

            with patch.object(craft, "parse_page",
                              side_effect=[[parsed_row("1", "件一")], [parsed_row("1", "件二")]]), \
                 patch.object(craft, "meta_of", side_effect=page_meta):
                tables = craft.build_tables(str(cache), only_names={"MAIN"})

        self.assertEqual(len(tables), 2)
        self.assertEqual([t["meta"]["name"] for t in tables.values()], ["装配一", "装配二"])

    def test_note_row_without_part_number_is_not_material(self):
        table = {
            "meta": {"drawing": "GDL161-300-20"},
            "records": [{"name": ("注：如图制作29套，镜像制作29套。", 0.99)}],
        }
        self.assertEqual(craft.process_doc(table), [])

    def test_root_manufacturing_quantity_propagates_to_children(self):
        record = {"qty": 2, "std": ""}
        root = craft.build_tree([record], {}, "GDL161-300-09", root_qty=6)
        child = root.children[0]
        self.assertEqual(child.mult, 6)
        self.assertEqual(craft.safe_product(child.row["qty"], child.mult), 12)

    def test_r257_heat_resistant_material_keeps_pdf_single_zero(self):
        table = {
            "meta": {"drawing": "GDL161-300-28-A"},
            "records": [{
                "seq": ("1", 0.99), "qty": ("1", 0.99),
                "name": ("热轧圆钢", 0.99), "material": ("0Cr25Ni20", 0.99),
                "weight": ("0.8", 0.99),
            }],
        }
        row = craft.process_doc(table)[0]
        self.assertEqual(row["material"], "0Cr25Ni20")

    def test_confirmed_quantity_correction_clears_old_review_flag(self):
        row = {
            "doc_drawing": "GDL161-300-26", "name": "热轧圆钢",
            "spec": "Ø14 L=640", "material": "00Cr25Ni20",
            "qty": None, "weight": 0.77, "qty_review": "旧的OCR冲突",
        }
        craft.apply_corrections([row], [{
            "drawing": "GDL161-300-26", "name": "热轧圆钢", "set": {"qty": 1}
        }])
        self.assertEqual(row["qty"], 1)
        self.assertEqual(row["qty_review"], "")


if __name__ == "__main__":
    unittest.main()
