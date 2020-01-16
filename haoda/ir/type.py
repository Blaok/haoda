import haoda.util

TYPE_WIDTH = {'float': 32, 'double': 64, 'half': 16}

class Type:
  
  def __init__(self, t: str):
    self.val = t

  def get_c_type(self) -> str:
    if self.val in {
        'uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64'
    }:
      return self.val + '_t'
    if self.val is None:
      return None
    if self.val == 'float32':
      return 'float'
    if self.val == 'float64':
      return 'double'
    for token in ('int', 'uint'):
      if self.val.startswith(token):
        bits = self.val.replace(token, '').split('_')
        if len(bits) > 1:
          assert len(bits) == 2
          return 'ap_{}<{}, {}>'.format(token.replace('int', 'fixed'), *bits)
        assert len(bits) == 1
        return 'ap_{}<{}>'.format(token, *bits)
    return self.val

  def get_width_in_bits(self) -> int:
    if isinstance(self.val, str):
      if self.val in TYPE_WIDTH:
        return TYPE_WIDTH[self.val]
      for prefix in 'uint', 'int', 'float':
        if self.val.startswith(prefix):
          return int(self.val.lstrip(prefix).split('_')[0])
    else:
      if hasattr(self.val, 'haoda_type'):
        return self.get_width_in_bits(self.val.haoda_type)
    raise haoda.util.InternalError('unknown haoda type: %s' % self.val)

  def get_width_in_bytes(self) -> int:
    return (self.get_width_in_bits() - 1) // 8 + 1

  def __eq__(self, other) -> bool:
    if not isinstance(other, Type):
      return NotImplemented
    if self.is_float():
      width = TYPE_WIDTH.get(self.val)
      if width is not None:
        self.val = 'float%d' % width
    if other.is_float():
      width = TYPE_WIDTH.get(other.val)
      if width is not None:
        other.val = 'float%d' % width
    return self.val == other.val

  def common_type(self, other: Type) -> str:
    """Return the common type of two operands.

    TODO: Consider fractional.

    Args:
      lhs: Haoda type of operand 1.
      rhs: Haoda type of operand 2.

    Returns:
      The common type of two operands.
    """
    if self.is_float() and not other.is_float():
      return self.val
    if other.is_float() and not self.is_float():
      return other.val
    if self.get_width_in_bits() < other.get_width_in_bits():
      return other.val
    return self.val

  def is_float(self) -> bool:
    return self.val in {'half', 'double'} or self.val.startswith('float')

  def is_fixed(self) -> bool:
    for token in ('int', 'uint'):
      if self.val.startswith(token):
        bits = self.val.replace(token, '').split('_')
        if len(bits) > 1:
          return True
    return False