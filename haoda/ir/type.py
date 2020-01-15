class HaodaType:

  def get_c_type(haoda_type: str) -> str:
    if haoda_type in {
        'uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64'
    }:
      return haoda_type + '_t'
    if haoda_type is None:
      return None
    if haoda_type == 'float32':
      return 'float'
    if haoda_type == 'float64':
      return 'double'
    for token in ('int', 'uint'):
      if haoda_type.startswith(token):
        bits = haoda_type.replace(token, '').split('_')
        if len(bits) > 1:
          assert len(bits) == 2
          return 'ap_{}<{}, {}>'.format(token.replace('int', 'fixed'), *bits)
        assert len(bits) == 1
        return 'ap_{}<{}>'.format(token, *bits)
    return haoda_type

  def get_width_in_bits(haoda_type: str) -> int:
    if isinstance(haoda_type, str):
      if haoda_type in TYPE_WIDTH:
        return TYPE_WIDTH[haoda_type]
      for prefix in 'uint', 'int', 'float':
        if haoda_type.startswith(prefix):
          return int(haoda_type.lstrip(prefix).split('_')[0])
    else:
      if hasattr(haoda_type, 'haoda_type'):
        return get_width_in_bits(haoda_type.haoda_type)
    raise InternalError('unknown haoda type: %s' % haoda_type)

  def get_width_in_bytes(haoda_type: str) -> int:
    return (get_width_in_bits(haoda_type) - 1) // 8 + 1

  def same_type(lhs: str, rhs: str) -> bool:
    if is_float(lhs):
      width = TYPE_WIDTH.get(lhs)
      if width is not None:
        lhs = 'float%d' % width
    if is_float(rhs):
      width = TYPE_WIDTH.get(rhs)
      if width is not None:
        rhs = 'float%d' % width
    return lhs == rhs

  def common_type(lhs: str, rhs: str) -> str:
    """Return the common type of two operands.

    TODO: Consider fractional.

    Args:
      lhs: Haoda type of operand 1.
      rhs: Haoda type of operand 2.

    Returns:
      The common type of two operands.
    """
    if is_float(lhs) and not is_float(rhs):
      return lhs
    if is_float(rhs) and not is_float(lhs):
      return rhs
    if get_width_in_bits(lhs) < get_width_in_bits(rhs):
      return rhs
    return lhs

  def is_float(haoda_type: str) -> bool:
    return haoda_type in {'half', 'double'} or haoda_type.startswith('float')

  def is_fixed(haoda_type: str) -> bool:
    for token in ('int', 'uint'):
      if haoda_type.startswith(token):
        bits = haoda_type.replace(token, '').split('_')
        if len(bits) > 1:
          return True
    return False