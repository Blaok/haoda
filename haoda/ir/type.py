from typing import Any, Iterable, Iterator, Optional

from cached_property import cached_property

import haoda.util

TYPE_WIDTH = {'float': 32, 'double': 64, 'half': 16}
HAODA_TYPE_TO_CL_TYPE = {
    'uint8': 'uchar',
    'uint16': 'ushort',
    'uint32': 'uint',
    'uint64': 'ulong',
    'int8': 'char',
    'int16': 'short',
    'int32': 'int',
    'int64': 'long',
    'half': 'half',
    'float': 'float',
    'double': 'double',
    'float16': 'half',
    'float32': 'float',
    'float64': 'double',
}


class Type:

  def __init__(self, val: Optional[str]):
    if not isinstance(val, (str, type(None))):
      raise TypeError('Type can only be constructed from str or NoneType, '
                      'got ' + type(val).__name__)
    self._val = val

  def __str__(self) -> str:
    return str(self._val)

  def __hash__(self) -> int:
    if self._val is None:
      return hash(None)
    return self.width_in_bits

  def __eq__(self, other: Any) -> bool:
    if isinstance(other, str):
      other = Type(other)
    elif not isinstance(other, Type):
      return NotImplemented
    self_val = self._val
    other_val = other._val
    if self.is_float:
      self_val = 'float%d' % self.width_in_bits
    if other.is_float:
      other_val = 'float%d' % other.width_in_bits
    return self_val == other_val

  @cached_property
  def c_type(self) -> Optional[str]:
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
    elif hasattr(self._val, 'haoda_type'):
      assert self._val is not None
      return self._val.haoda_type.width_in_bits
    raise haoda.util.InternalError('unknown haoda type: %s' % self._val)

  @cached_property
  def width_in_bytes(self) -> int:
    return (self.width_in_bits - 1) // 8 + 1

  def common_type(self, other: 'Type') -> 'Type':
    """Return the common type of two operands.

    TODO: Consider fractional.

    Args:
      lhs: Haoda type of operand 1.
      rhs: Haoda type of operand 2.

    Returns:
      The common type of two operands.
    """
    if self._val is None:
      return self
    # pylint: disable=protected-access
    if other._val is None:
      return other
    if self.is_float and not other.is_float:
      return self
    if other.is_float and not self.is_float:
      return other
    if self.width_in_bits < other.width_in_bits:
      return other
    return self

  @cached_property
  def is_float(self) -> bool:
    if self._val is None:
      return False
    return self._val in {'half', 'double'} or self._val.startswith('float')

  @cached_property
  def is_fixed(self) -> bool:
    if self._val is None:
      return False
    for token in ('int', 'uint'):
      if self._val.startswith(token):
        bits = self._val.replace(token, '').split('_')
        if len(bits) > 1:
          return True
    return False

  @cached_property
  def cl_type(self) -> Optional[str]:
    if self._val is None:
      return None
    cl_type = HAODA_TYPE_TO_CL_TYPE.get(self._val)
    if cl_type is not None:
      return cl_type
    return self._val + '_t'

  def get_cl_vec_type(self, burst_width: int) -> str:
    scalar_width = self.width_in_bits
    assert (burst_width % scalar_width == 0
           ), "burst width must be a multiple of width of the scalar type"
    assert (self._val in HAODA_TYPE_TO_CL_TYPE), "scalar type not supported"

    if burst_width == scalar_width:
      return HAODA_TYPE_TO_CL_TYPE[self._val]
    return HAODA_TYPE_TO_CL_TYPE[self._val] + str(burst_width // scalar_width)


class TupleType(Type):

  def __init__(self, val: Iterable[Type]):
    self._types = tuple(val)

  def __str__(self) -> str:
    return 'haoda_%s_tuple' % '_'.join(map(str, self._types))

  def __hash__(self) -> int:
    return hash(self._types)

  def __eq__(self, other: Any) -> bool:
    if not isinstance(other, Type):
      return NotImplemented
    if not isinstance(other, TupleType):
      return False
    return self._types == other._types

  def __getitem__(self, idx: int) -> Type:
    return self._types[idx]

  def __iter__(self) -> Iterator[Type]:
    return iter(self._types)

  def __len__(self) -> int:
    return len(self._types)

  @property
  def c_type(self) -> str:
    return 'haoda_tuple_%s' % '_'.join(x.c_type for x in self._types)

  @property
  def cl_type(self) -> str:
    return self.c_type

  @property
  def width_in_bits(self) -> int:
    return sum(x.width_in_bits for x in self._types)

  @property
  def c_type_def(self) -> str:
    return '\n'.join([
        f'struct __attribute__((packed)) {self.c_type} {{',
        *(f'  {t.c_type} val_{i};' for i, t in enumerate(self._types)),
        '};',
    ])

  @property
  def cl_type_def(self) -> str:
    return '\n'.join([
        'typedef struct __attribute__((packed)) {',
        *(f'  {t.cl_type} val_{i};' for i, t in enumerate(self._types)),
        f'}} {self.cl_type};',
    ])

  def common_type(self, other):
    raise TypeError

  @property
  def is_float(self) -> bool:
    raise TypeError

  @property
  def is_fixed(self) -> bool:
    raise TypeError

  def get_cl_vec_type(self, burst_width):
    raise TypeError
