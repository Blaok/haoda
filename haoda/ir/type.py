from typing import Any

from cached_property import cached_property

import haoda.util

TYPE_WIDTH = {'float': 32, 'double': 64, 'half': 16}

class Type:
  
  def __init__(self, t: str):
    self._val = t

  @cached_property
  def c_type(self) -> str:
    if self._val in {
        'uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64'
    }:
      return self._val + '_t'
    if self._val is None:
      return None
    if self._val == 'float32':
      return 'float'
    if self._val == 'float64':
      return 'double'
    for token in ('int', 'uint'):
      if self._val.startswith(token):
        bits = self._val.replace(token, '').split('_')
        if len(bits) > 1:
          assert len(bits) == 2
          return 'ap_{}<{}, {}>'.format(token.replace('int', 'fixed'), *bits)
        assert len(bits) == 1
        return 'ap_{}<{}>'.format(token, *bits)
    return self._val

  @cached_property
  def width_in_bits(self) -> int:
    if isinstance(self._val, str):
      if self._val in TYPE_WIDTH:
        return TYPE_WIDTH[self._val]
      for prefix in 'uint', 'int', 'float':
        if self._val.startswith(prefix):
          return int(self._val.lstrip(prefix).split('_')[0])
    else:
      if hasattr(self._val, 'haoda_type'):
        return self._val.haoda_type.width_in_bits
    raise haoda.util.InternalError('unknown haoda type: %s' % self._val)

  @cached_property
  def width_in_bytes(self) -> int:
    return (self.width_in_bits - 1) // 8 + 1

  def __eq__(self, other: Any) -> bool:
    if not isinstance(other, Type):
      if isinstance(other, str):
        other = Type(other)
      else:
        return NotImplemented
    if self.is_float:
      width = TYPE_WIDTH.get(self._val)
      if width is not None:
        self._val = 'float%d' % width
    if other.is_float():
      width = TYPE_WIDTH.get(other._val)
      if width is not None:
        other._val = 'float%d' % width
    return self._val == other._val

  def common_type(self, other: 'Type') -> 'Type':
    """Return the common type of two operands.

    TODO: Consider fractional.

    Args:
      lhs: Haoda type of operand 1.
      rhs: Haoda type of operand 2.

    Returns:
      The common type of two operands.
    """
    if self.is_float and not other.is_float:
      return self
    if other.is_float and not self.is_float:
      return other
    if self.width_in_bits < other.width_in_bits:
      return other
    return self

  @cached_property
  def is_float(self) -> bool:
    return self._val in {'half', 'double'} or self._val.startswith('float')

  @cached_property
  def is_fixed(self) -> bool:
    for token in ('int', 'uint'):
      if self._val.startswith(token):
        bits = self._val.replace(token, '').split('_')
        if len(bits) > 1:
          return True
    return False
