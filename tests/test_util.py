import unittest

from haoda import util
from haoda.ir.type import Type


class TestUtil(unittest.TestCase):

  def test_c_type(self):
    obj = Type('uint2')
    self.assertEqual(obj.get_c_type(), 'ap_uint<2>')
    obj = Type('int4')
    self.assertEqual(obj.get_c_type(), 'ap_int<4>')
    obj = Type('uint8')
    self.assertEqual(obj.get_c_type(), 'uint8_t')
    obj = Type('int16')
    self.assertEqual(obj.get_c_type(), 'int16_t')
    obj = Type('uint32_16')
    self.assertEqual(obj.get_c_type(), 'ap_ufixed<32, 16>')
    obj = Type('int64_32')
    self.assertEqual(obj.get_c_type(), 'ap_fixed<64, 32>')
    obj = Type('float')
    self.assertEqual(obj.get_c_type(), 'float')
    obj = Type('float32')
    self.assertEqual(obj.get_c_type(), 'float')
    obj = Type('float64')
    self.assertEqual(obj.get_c_type(), 'double')
    obj = Type('double')
    self.assertEqual(obj.get_c_type(), 'double')

  def test_type_propagation(self):
    self.assertEqual(util.get_suitable_int_type(15), 'uint4')
    self.assertEqual(util.get_suitable_int_type(16), 'uint5')
    self.assertEqual(util.get_suitable_int_type(15, -1), 'int5')
    self.assertEqual(util.get_suitable_int_type(16, -1), 'int6')
    self.assertEqual(util.get_suitable_int_type(0, -16), 'int5')
    self.assertEqual(util.get_suitable_int_type(0, -17), 'int6')
    self.assertEqual(util.get_suitable_int_type(15, -16), 'int5')
    self.assertEqual(util.get_suitable_int_type(15, -17), 'int6')
    self.assertEqual(util.get_suitable_int_type(16, -16), 'int6')


if __name__ == '__main__':
  unittest.main()
