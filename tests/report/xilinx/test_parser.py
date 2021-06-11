import io
import unittest

from haoda.report.xilinx import rtl


class TestParser(unittest.TestCase):

  def setUp(self):
    pass

  def test_dir_rpt(self):
    dir_rpt_file = io.StringIO(
        """Copyright 1986-2020 Xilinx, Inc. All Rights Reserved.
------------------------------------------------------------------------------------
| Tool Version : Vivado v.2020.2 (lin64) Build 3064766 Wed Nov 18 09:12:47 MST 2020
| Date         : Thu Jun 10 11:51:34 2021
| Host         : haodahost running 64-bit Ubuntu 18.04.5 LTS
| Command      : report_utilization -file report.rpt -hierarchical
| Design       : Top
| Device       : xcu280fsvh2892-2L
| Design State : Optimized
------------------------------------------------------------------------------------

Utilization Design Information

Table of Contents
-----------------
1. Utilization by Hierarchy

1. Utilization by Hierarchy
---------------------------

+-----------------------------------+------------------------------+------------+------------+---------+------+------+--------+--------+------+------------+
|              Instance             |            Module            | Total LUTs | Logic LUTs | LUTRAMs | SRLs |  FFs | RAMB36 | RAMB18 | URAM | DSP Blocks |
+-----------------------------------+------------------------------+------------+------------+---------+------+------+--------+--------+------+------------+
| Top                               |                        (top) |       8354 |       6026 |    2328 |    0 | 5005 |      2 |      1 |    4 |          3 |
|   (Top)                           |                        (top) |       1097 |       1097 |       0 |    0 | 4423 |      0 |      1 |    0 |          1 |
|   SubModule1                      |               Top_SubModule1 |       7176 |       4848 |    2328 |    0 |  582 |      2 |      0 |    0 |          1 |
|     SubSubModule1                 |            Top_SubSubModule1 |       7176 |       4848 |    2328 |    0 |  582 |      2 |      0 |    0 |          1 |
|   SubModule2                      |               Top_SubModule2 |         36 |         36 |       0 |    0 |    0 |      0 |      0 |    2 |          1 |
|   SubModule3                      |               Top_SubModule3 |         45 |         45 |       0 |    0 |    0 |      0 |      0 |    2 |          0 |
+-----------------------------------+------------------------------+------------+------------+---------+------+------+--------+--------+------+------------+
""")
    top_total = rtl.parse_hierarchical_utilization_report(dir_rpt_file)
    schema = top_total.schema

    self.assertDictEqual(
        schema,
        {
            'Module': 0,
            'Total LUTs': 1,
            'Logic LUTs': 2,
            'LUTRAMs': 3,
            'SRLs': 4,
            'FFs': 5,
            'RAMB36': 6,
            'RAMB18': 7,
            'URAM': 8,
            'DSP Blocks': 9,
        },
    )

    self.assertIsNone(top_total.parent)
    self.assertEqual(len(top_total.children), 4)
    self.assertEqual(top_total.instance, 'Top')
    self.assertEqual(top_total['Module'], '(top)')
    self.assertEqual(top_total['Total LUTs'], '8354')
    self.assertEqual(top_total['Logic LUTs'], '6026')
    self.assertEqual(top_total['LUTRAMs'], '2328')
    self.assertEqual(top_total['SRLs'], '0')
    self.assertEqual(top_total['FFs'], '5005')
    self.assertEqual(top_total['RAMB36'], '2')
    self.assertEqual(top_total['RAMB18'], '1')
    self.assertEqual(top_total['URAM'], '4')
    self.assertEqual(top_total['DSP Blocks'], '3')

    top_self, sub_module_1, sub_module_2, sub_module_3 = top_total.children

    self.assertIs(top_self.parent, top_total)
    self.assertListEqual(top_self.children, [])
    self.assertEqual(top_self.instance, '(Top)')
    self.assertIs(top_self.schema, schema)
    self.assertEqual(top_self['Module'], '(top)')
    self.assertEqual(top_self['Total LUTs'], '1097')
    self.assertEqual(top_self['Logic LUTs'], '1097')
    self.assertEqual(top_self['LUTRAMs'], '0')
    self.assertEqual(top_self['SRLs'], '0')
    self.assertEqual(top_self['FFs'], '4423')
    self.assertEqual(top_self['RAMB36'], '0')
    self.assertEqual(top_self['RAMB18'], '1')
    self.assertEqual(top_self['URAM'], '0')
    self.assertEqual(top_self['DSP Blocks'], '1')

    self.assertIs(sub_module_1.parent, top_total)
    self.assertEqual(len(sub_module_1.children), 1)
    self.assertEqual(sub_module_1.instance, 'SubModule1')
    self.assertIs(sub_module_1.schema, schema)
    self.assertEqual(sub_module_1['Module'], 'Top_SubModule1')
    self.assertEqual(sub_module_1['Total LUTs'], '7176')
    self.assertEqual(sub_module_1['Logic LUTs'], '4848')
    self.assertEqual(sub_module_1['LUTRAMs'], '2328')
    self.assertEqual(sub_module_1['SRLs'], '0')
    self.assertEqual(sub_module_1['FFs'], '582')
    self.assertEqual(sub_module_1['RAMB36'], '2')
    self.assertEqual(sub_module_1['RAMB18'], '0')
    self.assertEqual(sub_module_1['URAM'], '0')
    self.assertEqual(sub_module_1['DSP Blocks'], '1')

    sub_sub_module_1 = sub_module_1.children[0]

    self.assertIs(sub_sub_module_1.parent, sub_module_1)
    self.assertListEqual(sub_sub_module_1.children, [])
    self.assertEqual(sub_sub_module_1.instance, 'SubSubModule1')
    self.assertIs(sub_sub_module_1.schema, schema)
    self.assertEqual(sub_sub_module_1['Module'], 'Top_SubSubModule1')
    self.assertEqual(sub_sub_module_1['Total LUTs'], '7176')
    self.assertEqual(sub_sub_module_1['Logic LUTs'], '4848')
    self.assertEqual(sub_sub_module_1['LUTRAMs'], '2328')
    self.assertEqual(sub_sub_module_1['SRLs'], '0')
    self.assertEqual(sub_sub_module_1['FFs'], '582')
    self.assertEqual(sub_sub_module_1['RAMB36'], '2')
    self.assertEqual(sub_sub_module_1['RAMB18'], '0')
    self.assertEqual(sub_sub_module_1['URAM'], '0')
    self.assertEqual(sub_sub_module_1['DSP Blocks'], '1')

    self.assertIs(sub_module_2.parent, top_total)
    self.assertListEqual(sub_module_2.children, [])
    self.assertEqual(sub_module_2.instance, 'SubModule2')
    self.assertIs(sub_module_2.schema, schema)
    self.assertEqual(sub_module_2['Module'], 'Top_SubModule2')
    self.assertEqual(sub_module_2['Total LUTs'], '36')
    self.assertEqual(sub_module_2['Logic LUTs'], '36')
    self.assertEqual(sub_module_2['LUTRAMs'], '0')
    self.assertEqual(sub_module_2['SRLs'], '0')
    self.assertEqual(sub_module_2['FFs'], '0')
    self.assertEqual(sub_module_2['RAMB36'], '0')
    self.assertEqual(sub_module_2['RAMB18'], '0')
    self.assertEqual(sub_module_2['URAM'], '2')
    self.assertEqual(sub_module_2['DSP Blocks'], '1')

    self.assertIs(sub_module_3.parent, top_total)
    self.assertListEqual(sub_module_3.children, [])
    self.assertEqual(sub_module_3.instance, 'SubModule3')
    self.assertIs(sub_module_3.schema, schema)
    self.assertEqual(sub_module_3['Module'], 'Top_SubModule3')
    self.assertEqual(sub_module_3['Total LUTs'], '45')
    self.assertEqual(sub_module_3['Logic LUTs'], '45')
    self.assertEqual(sub_module_3['LUTRAMs'], '0')
    self.assertEqual(sub_module_3['SRLs'], '0')
    self.assertEqual(sub_module_3['FFs'], '0')
    self.assertEqual(sub_module_3['RAMB36'], '0')
    self.assertEqual(sub_module_3['RAMB18'], '0')
    self.assertEqual(sub_module_3['URAM'], '2')
    self.assertEqual(sub_module_3['DSP Blocks'], '0')
