# -*- coding: utf-8 -*-
"""用户规则第7条：同一父件下重名子件在名称后加序号（标准件不加）。

这条规则在 2026-09-05 那轮重写里被误删过一次（名称只剩 PDF 原文、序号没了），
这里加回归测试钉住，顺带覆盖共享子图记录不被重复编号、材质列不被序号污染。
"""
import importlib.util
import unittest
from pathlib import Path


PROGRAM = Path(__file__).resolve().parents[1] / "run.py"
spec = importlib.util.spec_from_file_location("craft_run_dup", PROGRAM)
craft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(craft)


class FakeNode:
    """只带 number_duplicate_names 需要的 row / parent。"""

    def __init__(self, row, parent=None):
        self.row = row
        self.parent = parent


def rec(name, std="", cat="", spec="", material=""):
    return {"name": name, "std": std, "cat": cat, "spec": spec,
            "material": material, "part_no": None, "ares": False}


class DuplicateNameNumberingTests(unittest.TestCase):
    def test_same_name_under_same_parent_gets_numbers(self):
        parent = FakeNode(rec("风机下导风板"))
        nodes = [FakeNode(rec("冷弯方形空心钢"), parent) for _ in range(3)]
        craft.number_duplicate_names(nodes)
        self.assertEqual([n.row["name"] for n in nodes],
                         ["冷弯方形空心钢1", "冷弯方形空心钢2", "冷弯方形空心钢3"])
        # 不带序号的原文名称要留在 name_base（型材材质列用它）
        self.assertEqual([n.row["name_base"] for n in nodes],
                         ["冷弯方形空心钢"] * 3)

    def test_standard_parts_are_not_numbered(self):
        parent = FakeNode(rec("风机下导风板"))
        nodes = [FakeNode(rec("六角头螺栓全螺纹", std="GB/T 5783"), parent) for _ in range(2)]
        craft.number_duplicate_names(nodes)
        self.assertEqual([n.row["name"] for n in nodes], ["六角头螺栓全螺纹"] * 2)

    def test_unique_name_is_untouched(self):
        parent = FakeNode(rec("风机下导风板"))
        node = FakeNode(rec("耐热钢板"), parent)
        craft.number_duplicate_names([node])
        self.assertEqual(node.row["name"], "耐热钢板")
        self.assertEqual(node.row["name_base"], "耐热钢板")

    def test_each_parent_counts_separately(self):
        p1, p2 = FakeNode(rec("A")), FakeNode(rec("B"))
        nodes = [FakeNode(rec("耐热钢板"), p1), FakeNode(rec("耐热钢板"), p1),
                 FakeNode(rec("耐热钢板"), p2)]
        craft.number_duplicate_names(nodes)
        self.assertEqual([n.row["name"] for n in nodes],
                         ["耐热钢板1", "耐热钢板2", "耐热钢板"])

    def test_shared_subtable_row_numbered_once(self):
        """同一子图被多个父件引用时记录字典共享，只能编一次号。"""
        shared = rec("冷弯方形空心钢")
        p1, p2 = FakeNode(rec("A")), FakeNode(rec("B"))
        a1 = FakeNode(shared, p1)
        a2 = FakeNode(rec("冷弯方形空心钢"), p1)
        b1 = FakeNode(shared, p2)
        craft.number_duplicate_names([a1, a2, b1])
        self.assertEqual(shared["name"], "冷弯方形空心钢1")
        self.assertEqual(shared["name_base"], "冷弯方形空心钢")
        self.assertEqual(a2.row["name"], "冷弯方形空心钢2")

    def test_profile_material_ignores_number(self):
        """型材材质列不能把序号粘到尺寸上（角钢1 + 50x50x5 → 150x50x5）。"""
        parent = FakeNode(rec("A"))
        r = rec("热轧等边角钢", spec="50x50x5 L=1630", material="Q235B")
        other = rec("热轧等边角钢", spec="63x63x6 L=1630", material="Q235B")
        craft.number_duplicate_names([FakeNode(r, parent), FakeNode(other, parent)])
        self.assertEqual(r["name"], "热轧等边角钢1")
        self.assertEqual(craft.material_of(r), "热轧等边角钢50x50x5/Q235B")


if __name__ == "__main__":
    unittest.main()
