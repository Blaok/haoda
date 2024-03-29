import collections
import copy
import logging
import math
from typing import Dict, List, Optional, Sequence, Tuple, Union

import cached_property

from haoda import ir, util
from haoda.ir import visitor

__all__ = (
    'AddSub',
    'BinaryAnd',
    'BinaryOp',
    'BinaryOr',
    'Call',
    'Cast',
    'DelayedRef',
    'DRAMRef',
    'EqCmp',
    'Expr',
    'FIFO',
    'FIFORef',
    'Let',
    'LogicAnd',
    'LtCmp',
    'Module',
    'ModuleTrait',
    'MulDiv',
    'Node',
    'Operand',
    'Pack',
    'Ref',
    'Unary',
    'Unpack',
    'Var',
    'Xor',
    'from_reduction',
    'get_max_val',
    'get_min_val',
    'is_const',
    'make_var',
    'parenthesize',
    'str2int',
    'to_reduction',
    'unparenthesize',
    'FUNC_NAME',
    'FUNCS',
    'GRAMMAR',
    'MATH_FUNCS',
    'OTHER_FUNCS',
    'REDUCTION_FUNCS',
    'REDUCTION_OPS',
    'STD_FUNCS',
)

_logger = logging.getLogger().getChild(__name__)

MATH_FUNCS = ('cos', 'sin', 'tan', 'acos', 'asin', 'atan', 'atan2', 'cosh',
              'sinh', 'tanh', 'acosh', 'asinh', 'atanh', 'exp', 'frexp',
              'ldexp', 'log', 'log10', 'modf', 'exp2', 'expm1', 'ilogb',
              'log1p', 'log2', 'logb', 'scalbn', 'scalbln', 'pow', 'sqrt',
              'cbrt', 'hypot', 'erf', 'erfc', 'tgamma', 'lgamma', 'ceil',
              'floor', 'fmod', 'trunc', 'round', 'lround', 'llround', 'rint',
              'lrint', 'llrint', 'nearbyint', 'remainder', 'remquo', 'copysign',
              'nan', 'nextafter', 'nexttoward', 'fdim', 'fmax', 'fmin', 'fabs',
              'fma')

STD_FUNCS = ('abs', 'labs', 'llabs', 'div', 'ldiv', 'lldiv', 'imaxabs',
             'imaxdiv')

OTHER_FUNCS = ('min', 'max', 'select')

FUNCS = (tuple(map('/{}[fl]?/'.format, MATH_FUNCS)) +
         tuple(map("'{}'".format, STD_FUNCS + OTHER_FUNCS)))

FUNC_NAME = 'FuncName: %s;' % '|'.join(FUNCS)

GRAMMAR = r'''
Bin: /0[Bb][01]+([Uu][Ll][Ll]?|[Ll]?[Ll]?[Uu]?)/;
Dec: /\d+([Uu][Ll][Ll]?|[Ll]?[Ll]?[Uu]?)/;
Oct: /0[0-7]+([Uu][Ll][Ll]?|[Ll]?[Ll]?[Uu]?)/;
Hex: /0[Xx][0-9a-fA-F]+([Uu][Ll][Ll]?|[Ll]?[Ll]?[Uu]?)/;
Int: ('+'|'-')?(Hex|Bin|Oct|Dec);
Float: /(((\d*\.\d+|\d+\.)([+-]?[Ee]\d+)?)|(\d+[+-]?[Ee]\d+))[FfLl]?/;
Num: Float|Int;

Type: FixedType | FloatType;
FixedType: /u?int[1-9]\d*(_[1-9]\d*)?/;
FloatType: /float[1-9]\d*(_[1-9]\d*)?/ | 'float' | 'double' | 'half';

Let: (haoda_type=Type)? name=ID '=' expr=Expr;
Ref: name=ID '(' idx=INT (',' idx=INT)* ')' ('~' lat=Int)?;

Expr: operand=LogicAnd (operator=LogicOrOp operand=LogicAnd)*;
LogicOrOp: '||';

LogicAnd: operand=BinaryOr (operator=LogicAndOp operand=BinaryOr)*;
LogicAndOp: '&&';

BinaryOr: operand=Xor (operator=BinaryOrOp operand=Xor)*;
BinaryOrOp: '|';

Xor: operand=BinaryAnd (operator=XorOp operand=BinaryAnd)*;
XorOp: '^';

BinaryAnd: operand=EqCmp (operator=BinaryAndOp operand=EqCmp)*;
BinaryAndOp: '&';

EqCmp: operand=LtCmp (operator=EqCmpOp operand=LtCmp)*;
EqCmpOp: '=='|'!=';

LtCmp: operand=AddSub (operator=LtCmpOp operand=AddSub)*;
LtCmpOp: '<='|'>='|'<'|'>';

AddSub: operand=MulDiv (operator=AddSubOp operand=MulDiv)*;
AddSubOp: '+'|'-';

MulDiv: operand=Unary (operator=MulDivOp operand=Unary)*;
MulDivOp: '*'|'/'|'%';

Unary: (operator=UnaryOp)* operand=Operand;
UnaryOp: '+'|'-'|'~'|'!';

Operand: cast=Cast | call=Call | ref=Ref | num=Num | var=Var | '(' expr=Expr ')';
Cast: haoda_type=Type '(' expr=Expr ')';
Call: name=FuncName '(' arg=Expr (',' arg=Expr)* ')';
Var: name=ID ('[' idx=Int ']')*;

''' + FUNC_NAME

# pylint: disable=protected-access


class Node:
  """A immutable, hashable IR node.
  """
  SCALAR_ATTRS: Tuple[str, ...] = ()
  LINEAR_ATTRS: Tuple[str, ...] = ()

  @property
  def ATTRS(self) -> Tuple[str, ...]:
    return self.SCALAR_ATTRS + self.LINEAR_ATTRS

  def __init__(self, **kwargs):
    self._haoda_type = None
    for attr in self.SCALAR_ATTRS:
      setattr(self, attr, kwargs.pop(attr))
    for attr in self.LINEAR_ATTRS:
      setattr(self, attr, tuple(kwargs.pop(attr)))

  def __hash__(self) -> int:
    return hash((tuple(getattr(self, _) for _ in self.SCALAR_ATTRS),
                 tuple(tuple(getattr(self, _)) for _ in self.LINEAR_ATTRS)))

  def __eq__(self, other) -> bool:
    if (getattr(self, 'haoda_type', None) is not None and
        getattr(other, 'haoda_type', None) is not None and
        self.haoda_type != other.haoda_type):
      return False
    return all(
        hasattr(other, attr) and getattr(self, attr) == getattr(other, attr)
        for attr in self.ATTRS)

  @property
  def c_type(self) -> str:
    return self.haoda_type.c_type

  @property
  def cl_type(self) -> str:
    return self.haoda_type.cl_type

  def _get_haoda_type(self) -> ir.Type:
    """This method may be overridden by subclasses."""
    return self._haoda_type

  @property
  def haoda_type(self) -> ir.Type:
    return self._get_haoda_type()

  @haoda_type.setter
  def haoda_type(self, val: Union[None, str, ir.Type]) -> None:
    if val is None:
      self._haoda_type = None
    elif isinstance(val, str):
      self._haoda_type = ir.Type(val)
    elif isinstance(val, ir.Type):
      self._haoda_type = val
    else:
      raise ValueError(
          'haoda_type must be set from an instance of NoneType, str, '
          'or haoda.ir.Type, got %s' % type(val))

  @property
  def width_in_bits(self) -> int:
    return self.haoda_type.width_in_bits

  @property
  def c_expr(self) -> str:
    return self._get_expr('c')

  @property
  def cl_expr(self) -> str:
    return self._get_expr('cl')

  def _get_expr(self, lang: str) -> str:
    raise NotImplementedError

  def _get_type_expr(self, lang: str) -> str:
    if lang == 'c':
      return self.c_type
    if lang == 'cl':
      return self.cl_type
    raise ValueError(f'lang must be "c" or "cl", got "{lang}"')

  def visit(self, callback, args=None, pre_recursion=None, post_recursion=None):
    """A general-purpose, flexible, and powerful visitor.

    The args parameter will be passed to the callback callable so that it may
    read or write any information from or to the caller.

    A copy of self will be made and passed to the callback to avoid destructive
    access.

    If a new object is returned by the callback, it will be returned directly
    without recursion.

    If the same object is returned by the callback, if any attribute is
    changed, it will not be recursively visited. If an attribute is unchanged,
    it will be recursively visited.
    """

    def callback_wrapper(callback, obj, args):
      if callback is None:
        return obj
      result = callback(obj, args)
      if result is not None:
        return result
      return obj

    self_copy = copy.copy(self)
    obj = callback_wrapper(callback, self_copy, args)
    if obj is not self_copy:
      return obj
    self_copy = callback_wrapper(pre_recursion, copy.copy(self), args)
    scalar_attrs = {
        attr: getattr(self_copy, attr).visit(
            callback, args, pre_recursion, post_recursion) if isinstance(
                getattr(self_copy, attr), Node) else getattr(self_copy, attr)
        for attr in self_copy.SCALAR_ATTRS
    }
    linear_attrs = {
        attr: tuple(
            _.visit(callback, args, pre_recursion, post_recursion
                   ) if isinstance(_, Node) else _
            for _ in getattr(self_copy, attr))
        for attr in self_copy.LINEAR_ATTRS
    }

    for attr in self.SCALAR_ATTRS:
      # old attribute may not exist in mutated object
      if not hasattr(obj, attr):
        continue
      if getattr(obj, attr) is getattr(self, attr):
        if isinstance(getattr(obj, attr), Node):
          setattr(obj, attr, scalar_attrs[attr])
    for attr in self.LINEAR_ATTRS:
      # old attribute may not exist in mutated object
      if not hasattr(obj, attr):
        continue
      setattr(
          obj, attr,
          tuple(c if a is b and isinstance(a, Node) else a for a, b, c in zip(
              getattr(obj, attr), getattr(self, attr), linear_attrs[attr])))
    return callback_wrapper(post_recursion, obj, args)


class Let(Node):
  SCALAR_ATTRS = 'haoda_type', 'name', 'expr'

  name: str
  expr: Node

  def __str__(self):
    result = '{} = {}'.format(self.name, unparenthesize(self.expr))
    if self.haoda_type is not None:
      result = '{} {}'.format(self.haoda_type, result)
    return result

  def _get_haoda_type(self):
    if self._haoda_type is None:
      return self.expr.haoda_type
    return self._haoda_type

  def _get_expr(self, lang: str):
    return 'const {} {} = {};'.format(self._get_type_expr(lang), self.name,
                                      unparenthesize(self.expr._get_expr(lang)))


class Ref(Node):
  SCALAR_ATTRS = 'name', 'lat'
  LINEAR_ATTRS = ('idx',)

  name: str
  idx: Sequence[int]
  lat: Optional[int]

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.idx = tuple(self.idx)
    if not hasattr(self, 'haoda_type'):
      self.haoda_type = None
    # self.lat will be defined in super().__init__(**kwargs)
    # pylint: disable=access-member-before-definition
    if isinstance(self.lat, str):
      self.lat = str2int(self.lat)

  def __str__(self):
    result = '{}({})'.format(self.name, ', '.join(map(str, self.idx)))
    if self.lat is not None:
      result += ' ~{}'.format(self.lat)
    return result


class BinaryOp(Node):
  LINEAR_ATTRS = 'operand', 'operator'

  operand: Sequence[Node]
  operator: Sequence[str]

  def __str__(self):
    result = str(self.operand[0])
    for operator, operand in zip(self.operator, self.operand[1:]):
      result += ' {} {}'.format(operator, operand)
    if self.singleton:
      return result
    return parenthesize(result)

  def _get_haoda_type(self):
    # TODO: derive from all operands
    return self.operand[0].haoda_type

  def _get_expr(self, lang: str) -> str:
    result = self.operand[0]._get_expr(lang)
    for operator, operand in zip(self.operator, self.operand[1:]):
      result += ' {} {}'.format(operator, operand._get_expr(lang))
    if self.singleton:
      return result
    return parenthesize(result)

  @property
  def singleton(self) -> bool:
    return len(self.operand) == 1  # type: ignore


class Expr(BinaryOp):
  pass


class LogicAnd(BinaryOp):
  pass


class BinaryOr(BinaryOp):
  pass


class Xor(BinaryOp):
  pass


class BinaryAnd(BinaryOp):
  pass


class EqCmp(BinaryOp):
  pass


class LtCmp(BinaryOp):
  pass


class AddSub(BinaryOp):
  '''
  def _get_haoda_type(self):
    if getattr(self, '_haoda_type', None) is None:

      # leave type undetermined if any child has undetermined type (None)
      for opd in self.operand:
        if opd.haoda_type is None:
          return None

      # use the biggest float if there is one
      float_types = {
          opd.haoda_type
          for opd in self.operand
          if opd.haoda_type.is_float
      }
      if float_types:
        for float_type, width in util.TYPE_WIDTH.items():
          if float_type in float_types:
            float_types.remove(float_type)
            float_types.add('float%d' % width)
        self._haoda_type = max(float_types, key=util.get_width_in_bits)
        return self._haoda_type

      # TODO: implement rules for fixed point non-interger numbers
      for opd in self.operand:
        if opd.haoda_type.is_fixed:
          self._haoda_type = opd.haoda_type
          return self._haoda_type

      # all operands are integers
      max_val = 0
      min_val = 0
      for opr, opd in zip(('+',) + self.operator, self.operand):
        if opr == '+':
          max_val += get_max_val(opd)
          min_val += get_min_val(opd)
        else:
          max_val -= get_min_val(opd)
          min_val -= get_max_val(opd)
      self._haoda_type = util.get_suitable_int_type(max_val, min_val)
    return self._haoda_type
  '''


class MulDiv(BinaryOp):
  '''
  @property
  def _get_haoda_type(self):
    if getattr(self, '_haoda_type', None) is None:

      # leave type undetermined if any child has undetermined type (None)
      for opd in self.operand:
        if opd.haoda_type is None:
          return None

      # use the biggest float if there is one
      float_types = {
          opd.haoda_type
          for opd in self.operand
          if opd.haoda_type.is_float
      }
      if float_types:
        for float_type, width in util.TYPE_WIDTH.items():
          if float_type in float_types:
            float_types.remove(float_type)
            float_types.add('float%d' % width)
        self._haoda_type = max(float_types, key=util.get_width_in_bits)
        return self._haoda_type

    # TODO: implement rules for fixed point non-interger numbers
      for opd in self.operand:
        if opd.haoda_type.is_fixed:
          self._haoda_type = opd.haoda_type
          return self._haoda_type

      # all operands are integers
      max_val = 1
      for opr, opd in zip(('*',) + self.operator, self.operand):
        if opr == '*':
          max_val *= max(abs(get_max_val(opd)), abs(get_min_val(opd)))
      self._haoda_type = util.get_suitable_int_type(max_val, -max_val)
    return self._haoda_type

  '''


class Unary(Node):
  SCALAR_ATTRS = ('operand',)
  LINEAR_ATTRS = ('operator',)

  operand: 'Operand'
  operator: Sequence[str]

  def __str__(self):
    return ''.join(self.operator) + str(self.operand)

  def _get_haoda_type(self):
    return self.operand.haoda_type

  def _get_expr(self, lang: str) -> str:
    return ''.join(self.operator) + self.operand._get_expr(lang)


class Operand(Node):
  SCALAR_ATTRS = 'cast', 'call', 'ref', 'num', 'var', 'expr'

  cast: Optional['Cast']
  call: Optional['Call']
  ref: Optional[Ref]
  num: Optional[str]
  var: Optional['Var']
  expr: Optional['Expr']

  def __str__(self):
    for attr in ('cast', 'call', 'ref', 'num', 'var'):
      if getattr(self, attr) is not None:
        return str(getattr(self, attr))
    # pylint: disable=useless-else-on-loop
    else:
      return parenthesize(self.expr)

  def _get_expr(self, lang: str) -> str:
    for attr_name in ('cast', 'call', 'ref', 'num', 'var'):
      attr = getattr(self, attr_name)
      if attr is not None:
        if hasattr(attr, '_get_expr'):
          return attr._get_expr(lang)
        return str(attr)
    # pylint: disable=useless-else-on-loop
    else:
      assert self.expr is not None
      return parenthesize(self.expr._get_expr(lang))

  def _get_haoda_type(self):
    for attr in self.ATTRS:
      val = getattr(self, attr)
      if val is not None:
        if hasattr(val, 'haoda_type'):
          return val.haoda_type
        if attr == 'num':
          if 'u' in val.lower():
            if 'll' in val.lower():
              return ir.Type('uint64')
            return ir.Type('uint32')
          if 'll' in val.lower():
            return ir.Type('int64')
          if 'fl' in val.lower():
            return ir.Type('double')
          if 'f' in val.lower() or 'e' in val.lower():
            return ir.Type('float')
          if '.' in val:
            return ir.Type('double')
          return ir.Type('int32')
        return None
    raise util.InternalError('undefined Operand')


class Cast(Node):
  SCALAR_ATTRS = 'haoda_type', 'expr'

  expr: Node

  def __str__(self):
    return '{}{}'.format(self.haoda_type, parenthesize(self.expr))

  def _get_expr(self, lang: str) -> str:
    return '({}){}'.format(self._get_type_expr(lang),
                           parenthesize(self.expr._get_expr(lang)))


class Call(Node):
  SCALAR_ATTRS = ('name',)
  LINEAR_ATTRS = ('arg',)

  name: str
  arg: Sequence[Node]

  def __str__(self):
    return '{}({})'.format(self.name, ', '.join(map(str, self.arg)))

  def _get_haoda_type(self):
    if self.name in ('select',):
      if any(self.arg[idx].haoda_type is None for idx in (1, 2)):
        return None
      return self.arg[1].haoda_type.common_type(self.arg[2].haoda_type)
    return self.arg[0].haoda_type

  def _get_expr(self, lang: str) -> str:
    if self.name in {'min', 'max'}:
      assert len(self.arg) >= 2, 'too few arguments to %s' % self.name

      if lang == 'c':
        fmt_str = 'std::{}({}, {})'

        def variadic_to_binary_c(args: List[str]) -> str:
          nargs = len(args)
          if nargs == 1:
            return args[0]
          if nargs == 2:
            return fmt_str.format(self.name, *args)
          return fmt_str.format(self.name,
                                variadic_to_binary_c(args[:nargs // 2]),
                                variadic_to_binary_c(args[nargs // 2:]))

        return variadic_to_binary_c([_.c_expr for _ in self.arg])

      if lang == 'cl':
        fmt_str = '{}({}, {})'

        def variadic_to_binary_cl(args: Sequence[Node]) -> Tuple[str, bool]:
          nargs = len(args)
          func_name = self.name
          if nargs == 1:
            return args[0].cl_expr, args[0].haoda_type.is_float
          if nargs == 2:
            is_float = any(x.haoda_type.is_float for x in args)
            if is_float:
              func_name = f'f{func_name}'
            return fmt_str.format(func_name,
                                  *(x.cl_expr for x in args)), is_float
          arg1, is_float1 = variadic_to_binary_cl(args[:nargs // 2])
          arg2, is_float2 = variadic_to_binary_cl(args[nargs // 2:])
          return fmt_str.format(func_name, arg1, arg2), is_float1 or is_float2

        return variadic_to_binary_cl(self.arg)[0]

    if self.name == 'select':
      common_type = self.arg[1].haoda_type.common_type(self.arg[2].haoda_type)
      args = list(self.arg)
      for idx in 1, 2:
        if args[idx].haoda_type != common_type:
          args[idx] = Cast(haoda_type=common_type, expr=args[idx])
      return '({} ? {} : {})'.format(*(x._get_expr(lang) for x in args))
    return '{}({})'.format(self.name,
                           ', '.join(x._get_expr(lang) for x in self.arg))


class Var(Node):
  SCALAR_ATTRS = ('name',)
  LINEAR_ATTRS = ('idx',)

  name: str
  idx: Sequence[int]

  def __str__(self):
    return self.name + ''.join(map('[{}]'.format, self.idx))

  def _get_expr(self, lang: str) -> str:
    return self.name + ''.join(map('[{}]'.format, self.idx))


class FIFO(Node):
  """A reference to another node in a haoda.ir.Expr.

  This is used to represent a read/write from/to a Module in an output's Expr.
  It replaces Ref in haoda.ir, which is used to represent an element
  reference to a tensor.

  Attributes:
    read_module: Module reading from this FIFO.
    read_lat: int, at what cycle of a pipelined loop it is being read.
    write_module: Module writing to this FIFO.
    write_lat: int, at what cycle of a pipelined loop it is being written.
    depth: int, FIFO depth.
  """
  IMMUTABLE_ATTRS = 'read_module', 'write_module'
  SCALAR_ATTRS = 'read_module', 'read_lat', 'write_module', 'write_lat', 'depth'

  read_module: 'Module'
  read_lat: Optional[int]
  write_module: 'Module'
  write_lat: Optional[int]
  depth: Optional[int]

  def __init__(self,
               write_module,
               read_module,
               depth=None,
               write_lat=None,
               read_lat=None):
    super().__init__(write_module=write_module,
                     read_module=read_module,
                     depth=depth,
                     write_lat=write_lat,
                     read_lat=read_lat)

  def __repr__(self):
    return 'fifo[%d]: %s%s => %s%s' % (
        self.depth, repr(self.write_module), '' if self.write_lat is None else
        ' ~%s' % self.write_lat, repr(self.read_module),
        '' if self.read_lat is None else ' ~%s' % self.read_lat)

  def __hash__(self):
    return hash(tuple(getattr(self, _) for _ in self.IMMUTABLE_ATTRS))

  def __eq__(self, other):
    return all(
        getattr(self, _) == getattr(other, _)
        for _ in type(self).IMMUTABLE_ATTRS)

  @property
  def edge(self):
    return self.write_module, self.read_module

  def _get_haoda_type(self):
    return self.write_module.exprs[self].haoda_type

  def _get_expr(self, tag: str):
    return 'from_{}_to_{}'.format(self.write_module.name, self.read_module.name)


class Module():
  """A node in the dataflow graph.

  This is the base class for a dataflow module. It defines the parent (input)
  nodes, children (output) nodes, output expressions, input schedules, and
  output schedules. It also has a name to help identify itself.

  Attributes:
    parents: Set of parent (input) Module.
    children: Set of child (output) Module.
    lets: List of haoda.ir.Let expressions.
    exprs: Dict of {FIFO: haoda.ir.Expr}, stores an output's expression.
  """

  _id_dict = {}

  def __init__(self, name: str = ''):
    """Initializes attributes into empty list or dict.

    Args:
      name: Specify a name for the module. Unlike the default name generated
        based on a global sequential unique ID, the user is responsible for
        making sure the name is unique (if that is desired).
    """
    self.parents = []
    self.children = []
    self.lets = []
    self.exprs: Dict[FIFO, ir.Node] = {}
    self._name = name

  @property
  def name(self):
    if self._name:
      return self._name
    id_ = Module._id_dict.setdefault(id(self), len(Module._id_dict))
    return f'module_{id_}'

  @property
  def fifos(self):
    return tuple(self.exprs.keys())

  @property
  def fifo_dict(self):
    return {(self, fifo.read_module): fifo for fifo in self.exprs}

  def fifo(self, dst_node):
    return self.fifo_dict[(self, dst_node)]

  def get_latency(self, dst_node):
    return self.fifo(dst_node).write_lat or 0

  def visit_loads(self, callback, args=None):
    obj = copy.copy(self)
    obj.lets = tuple(_.visit(callback, args) for _ in self.lets)
    obj.exprs = collections.OrderedDict()
    for fifo in self.exprs:
      obj.exprs[fifo] = self.exprs[fifo].visit(callback, args)
    return obj

  @property
  def dram_reads(self) -> Tuple[Tuple['DRAMRef', int], ...]:
    return self._interfaces['dram_reads']

  @property
  def dram_writes(self) -> Tuple[Tuple['DRAMRef', int], ...]:
    return self._interfaces['dram_writes']

  @property
  def input_fifos(self) -> Tuple[str, ...]:
    return self._interfaces['input_fifos']

  @property
  def output_fifos(self) -> Tuple[str, ...]:
    return self._interfaces['output_fifos']

  @cached_property.cached_property
  def _interfaces(self):
    # find dram reads
    reads_in_lets = tuple(_.expr for _ in self.lets)
    reads_in_exprs = tuple(self.exprs.values())
    dram_reads = collections.OrderedDict()
    for dram_ref in visitor.get_dram_refs(reads_in_lets + reads_in_exprs):
      for bank in dram_ref.dram:
        dram_reads[(dram_ref.var, bank)] = (dram_ref, bank)
    dram_reads = tuple(dram_reads.values())

    # find dram writes
    writes_in_lets = tuple(
        _.name for _ in self.lets if not isinstance(_.name, str))
    dram_writes = collections.OrderedDict()
    for dram_ref in visitor.get_dram_refs(writes_in_lets):
      for bank in dram_ref.dram:
        dram_writes[(dram_ref.var, bank)] = (dram_ref, bank)
    dram_writes = tuple(dram_writes.values())

    output_fifos = tuple(_.c_expr for _ in self.exprs)
    input_fifos = tuple(_.c_expr for _ in visitor.get_read_fifo_set(self))

    return {
        'dram_writes': dram_writes,
        'output_fifos': output_fifos,
        'input_fifos': input_fifos,
        'dram_reads': dram_reads
    }

  def __str__(self):
    return f'{self.name}: {self.__dict__}'

  def __repr__(self):
    return self.name

  def add_child(self, child):
    """Add a child (low level).

    This method only handles children and parents field; lets and exprs are
    not updated.

    Arguments:
      child: Module, child being added
    """
    if child not in self.children:
      self.children.append(child)
    if self not in child.parents:
      child.parents.append(self)

  def bfs_node_gen(self):
    """BFS over descendant nodes.

    This method is a BFS traversal generator over all descendant nodes.
    """
    node_queue = collections.deque([self])
    seen_nodes = {self}
    while node_queue:
      node = node_queue.popleft()
      yield node
      for child in node.children:
        if child not in seen_nodes:
          node_queue.append(child)
          seen_nodes.add(child)

  def dfs_node_gen(self):
    """DFS over descendant nodes.

    This method is a DFS traversal generator over all descendant nodes.
    """
    node_stack = [self]
    seen_nodes = {self}
    while node_stack:
      node = node_stack.pop()
      yield node
      for child in node.children:
        if child not in seen_nodes:
          node_stack.append(child)
          seen_nodes.add(child)

  def tpo_node_gen(self):
    """Traverse descendant nodes in topological order.

    This method is a generator that traverses all descendant nodes in
    topological order.
    """
    nodes = collections.OrderedDict()
    for node in self.bfs_node_gen():
      nodes[node] = len(node.parents)
    while nodes:
      for node in nodes:
        if nodes[node] == 0:
          yield node
          for child in node.children:
            nodes[child] -= 1
          del nodes[node]
          break
      else:
        return

  def bfs_edge_gen(self):
    """BFS over descendant edges.

    This method is a BFS traversal generator over all descendant edges.
    """
    node_queue = collections.deque([self])
    seen_nodes = {self}
    while node_queue:
      node = node_queue.popleft()
      for child in node.children:
        yield node, child
        if child not in seen_nodes:
          node_queue.append(child)
          seen_nodes.add(child)

  def dfs_edge_gen(self):
    """DFS over descendant edges.

    This method is a DFS traversal generator over all descendant edges.
    """
    node_stack = [self]
    seen_nodes = {self}
    while node_stack:
      node = node_stack.pop()
      for child in node.children:
        yield node, child
        if child not in seen_nodes:
          node_stack.append(child)
          seen_nodes.add(child)

  def get_descendants(self):
    """Get all descendant nodes.

    This method returns all descendant nodes as a set.

    Returns:
      Set of descendant Module.
    """
    return {self}.union(*map(Module.get_descendants, self.children))

  def get_connections(self):
    """Get all descendant edges.

    This method returns all descendant edges as a set.

    Returns:
      Set of descendant (src Module, dst Module) tuple.
    """
    return ({(self, child) for child in self.children
            }.union(*map(Module.get_connections, self.children)))


class DelayedRef(Node):
  """A delayed Node reference.

  Attributes:
    delay: int
    ref: Node
  """
  SCALAR_ATTRS = ('delay', 'ref')

  delay: int
  ref: Ref

  def _get_haoda_type(self):
    return self.ref.haoda_type

  def __str__(self):
    return '%s delayed %d' % (self.ref, self.delay)

  def __repr__(self):
    return str(self)

  def __hash__(self):
    return hash((self.delay, self.ref))

  def __eq__(self, other):
    return all(
        getattr(self, attr) == getattr(other, attr)
        for attr in ('delay', 'ref'))

  @property
  def identifier(self) -> str:
    ref = getattr(self.ref, 'identifier', self.ref.c_expr)
    return f'{ref}_delayed_{self.delay}'

  @property
  def buf_name(self):
    return f'{self.identifier}_buf'

  @property
  def ptr(self):
    return f'ptr_delay_{self.delay}'

  @property
  def ptr_type(self):
    return ir.Type('uint%d' % max(self.delay - 1, 1).bit_length())

  def _get_expr(self, lang: str) -> str:
    return self.identifier

  @property
  def c_ptr_type(self):
    return self.ptr_type.c_type

  @property
  def cl_ptr_type(self):
    return self.ptr_type.cl_type

  @property
  def c_ptr_decl(self):
    return '{} {} = 0;'.format(self.c_ptr_type, self.ptr)

  @property
  def cl_ptr_decl(self):
    return '{} {} = 0;'.format(self.cl_ptr_type, self.ptr)

  @property
  def c_buf_ref(self):
    return '{}[{}]'.format(self.buf_name, self.ptr)

  @property
  def c_buf_decl(self):
    return '{} {}[{}];'.format(self.c_type, self.buf_name, self.delay)

  @property
  def cl_buf_decl(self):
    return '{} {}[{}];'.format(self.cl_type, self.buf_name, self.delay)

  @property
  def c_buf_load(self):
    return '{} = {};'.format(self.c_expr, self.c_buf_ref)

  @property
  def cl_buf_load(self):
    return f'{self.cl_expr} = {self.c_buf_ref};'

  @property
  def c_buf_store(self):
    return '{} = {};'.format(self.c_buf_ref, self.ref.c_expr)

  @property
  def cl_buf_store(self):
    return f'{self.c_buf_ref} = {self.ref.cl_expr};'

  @property
  def c_next_ptr_expr(self):
    return '{ptr} < {depth} ? (++{ptr}) : ({ptr} = 0)'.format(
        ptr=self.ptr, c_ptr_type=self.c_ptr_type, depth=self.delay - 1)

  @property
  def cl_next_ptr_expr(self):
    return '{ptr} < {depth} ? (++{ptr}) : ({ptr} = 0)'.format(
        ptr=self.ptr, ptr_type=self.cl_ptr_type, depth=self.delay - 1)


class FIFORef(Node):
  """A FIFO reference.

  Attributes:
    fifo: FIFO it is linked to
    lat: int, at what cycle of a pipelined loop it is being referenced.
    ref_id: int, reference id in the current scope
  Properties:
    ld_name: str
    st_name: str
    ref_name: str
  """
  SCALAR_ATTRS = ('fifo', 'lat', 'ref_id')
  LD_PREFIX = 'fifo_ld_'
  ST_PREFIX = 'fifo_st_'
  REF_PREFIX = 'fifo_ref_'

  def __str__(self):
    return '<%s fifo_ref_%d%s>' % (self.haoda_type, self.ref_id,
                                   '@%s' % self.lat if self.lat else '')

  def __repr__(self):
    return str(self)

  def __hash__(self):
    return hash((self.lat, self.ref_id))

  def __eq__(self, other):
    if (self.haoda_type is not None and other.haoda_type is not None and
        self.haoda_type != other.haoda_type):
      return False
    return all(
        getattr(self, attr) == getattr(other, attr)
        for attr in ('lat', 'ref_id'))

  def _get_haoda_type(self):
    return self.fifo.haoda_type

  @property
  def ld_name(self):
    return '{}{}'.format(type(self).LD_PREFIX, self.ref_id)

  @property
  def ref_name(self):
    return '{}{}'.format(type(self).REF_PREFIX, self.ref_id)

  def _get_expr(self, lang: str) -> str:
    return self.ref_name


class DRAMRef(Node):
  """A DRAM reference.

  Attributes:
    haoda_type: str
    dram: [int], DRAM id it is accessing
    var: str, variable name it is accessing
    offset: int
  """
  SCALAR_ATTRS = 'haoda_type', 'dram', 'var', 'offset'

  def __str__(self):
    return 'dram<bank {} {}@{}>'.format(util.lst2str(self.dram), self.var,
                                        self.offset)

  def __repr__(self):
    return str(self)

  def __hash__(self):
    return hash((self.var, self.dram, self.offset))

  def __eq__(self, other):
    if (self.haoda_type is not None and other.haoda_type is not None and
        self.haoda_type != other.haoda_type):
      return False
    return all(
        getattr(self, attr) == getattr(other, attr)
        for attr in ('var', 'dram', 'offset'))

  def _get_expr(self, lang: str) -> str:
    return str(self)

  def dram_buf_name(self, bank):
    assert bank in self.dram, 'unexpected bank {}'.format(bank)
    return 'dram_{}_bank_{}_buf'.format(self.var, bank)

  def dram_fifo_name(self, bank):
    assert bank in self.dram, 'unexpected bank {}'.format(bank)
    return 'dram_{}_bank_{}_fifo'.format(self.var, bank)


class ModuleTrait(Node):
  """A immutable, hashable trait of a dataflow module.

  Attributes:
    lets: tuple of lets
    exprs: tuple of exprs
    template_types: tuple of template types (TODO)
    template_ints: tuple of template ints (TODO)

  Properties:
    loads: tuple of FIFORefs
  """
  LINEAR_ATTRS = ('lets', 'exprs', 'template_types', 'template_ints')

  def __init__(self, node):

    def mutate(obj, loads):
      if isinstance(obj, FIFO):
        if loads:
          if obj not in loads:
            load_id = next(reversed(loads.values())).ref_id + 1
          else:
            return loads[obj]
        else:
          load_id = 0
        fifo_ref = FIFORef(fifo=obj, lat=obj.read_lat, ref_id=load_id)
        loads[obj] = fifo_ref
        return fifo_ref
      return obj

    loads = collections.OrderedDict()
    node = node.visit_loads(mutate, loads)
    self.loads = tuple(loads.values())
    super().__init__(lets=tuple(node.lets),
                     exprs=tuple(node.exprs.values()),
                     template_types=tuple(),
                     template_ints=tuple())
    _logger.debug('Signature: %s', self)

  def __repr__(self):
    return '%s(loads: %s, lets: %s, exprs: %s)' % (
        type(self).__name__, util.idx2str(self.loads), util.idx2str(
            self.lets), util.idx2str(self.exprs))

  @property
  def dram_reads(self):
    return self._interfaces['dram_reads']

  @property
  def dram_writes(self):
    return self._interfaces['dram_writes']

  @property
  def input_fifos(self):
    return self._interfaces['input_fifos']

  @property
  def output_fifos(self):
    return self._interfaces['output_fifos']

  @cached_property.cached_property
  def _interfaces(self):
    # find dram reads
    reads_in_lets = tuple(_.expr for _ in self.lets)
    reads_in_exprs = tuple(self.exprs)
    dram_reads = collections.OrderedDict()
    for dram_ref in visitor.get_dram_refs(reads_in_lets + reads_in_exprs):
      for bank in dram_ref.dram:
        dram_reads[(dram_ref.var, bank)] = (dram_ref, bank)
    dram_reads = tuple(dram_reads.values())

    # find dram writes
    writes_in_lets = tuple(
        _.name for _ in self.lets if not isinstance(_.name, str))
    dram_writes = collections.OrderedDict()
    for dram_ref in visitor.get_dram_refs(writes_in_lets):
      for bank in dram_ref.dram:
        dram_writes[(dram_ref.var, bank)] = (dram_ref, bank)
    dram_writes = tuple(dram_writes.values())

    output_fifos = tuple('{}{}'.format(FIFORef.ST_PREFIX, idx)
                         for idx, expr in enumerate(self.exprs))
    input_fifos = tuple(_.ld_name for _ in self.loads)

    return {
        'dram_writes': dram_writes,
        'output_fifos': output_fifos,
        'input_fifos': input_fifos,
        'dram_reads': dram_reads
    }


class Pack(Node):
  LINEAR_ATTRS = ('exprs',)

  exprs: Sequence[Node]

  _name_dict = {}

  def __str__(self) -> str:
    return '{%s}' % ', '.join(map(str, self.exprs))

  def _get_haoda_type(self) -> ir.TupleType:
    return ir.TupleType(x.haoda_type for x in self.exprs)

  def _get_expr(self, lang: str) -> str:
    args = ', '.join(x._get_expr(lang) for x in self.exprs)
    if lang == 'c':
      return f'{{{args}}}'
    if lang == 'cl':
      return f'({self.cl_type}){{{args}}}'
    raise NotImplementedError

  @property
  def identifier(self) -> str:
    long_name = '_'.join(getattr(x, 'identifier', x.c_expr) for x in self.exprs)
    short_name = Pack._name_dict.setdefault(long_name, len(Pack._name_dict))
    return 'pack_%d' % short_name


class Unpack(Node):
  SCALAR_ATTRS = ('expr', 'idx')

  expr: Node
  idx: int

  def __str__(self) -> str:
    return f'{{{self.expr}}}[{self.idx}]'

  def _get_haoda_type(self) -> ir.Type:
    assert isinstance(self.expr.haoda_type, ir.TupleType)
    return self.expr.haoda_type[self.idx]

  def _get_expr(self, lang: str) -> str:
    return f'{self.expr._get_expr(lang)}.val_{self.idx}'

  @property
  def identifier(self) -> str:
    expr = getattr(self.expr, 'identifier', self.expr.c_expr)
    return f'{expr}_val_{self.idx}'


def make_var(val, haoda_type: Optional[ir.Type] = None):
  """Make literal Var from val."""
  var = Var(name=val, idx=())
  if haoda_type is not None:
    var.haoda_type = haoda_type
  return var


def is_const(node: Node) -> bool:
  if isinstance(node, Operand) and getattr(node, 'num') is not None:
    return True
  return False


def str2int(s, none_val=None):
  if s is None:
    return none_val
  while s[-1] in 'UuLl':
    s = s[:-1]
  if s[0:2] == '0x' or s[0:2] == '0X':
    return int(s, 16)
  if s[0:2] == '0b' or s[0:2] == '0B':
    return int(s, 2)
  if s[0] == '0':
    return int(s, 8)
  return int(s)


def parenthesize(expr) -> str:
  return '({})'.format(unparenthesize(expr))


def unparenthesize(expr) -> str:
  expr_str = str(expr)
  while expr_str.startswith('(') and expr_str.endswith(')'):
    count = 1
    for char in expr_str[1:-1]:
      if char == '(':
        count += 1
      elif char == ')':
        count -= 1
      if count == 0:  # the outermost parentheses are not paired
        return expr_str
    expr_str = expr_str[1:-1]
  return expr_str


def get_result_type(operand1, operand2, operator):
  for t in ('double', 'float') + sum(
      (('int%d_t' % w, 'uint%d_t' % w) for w in (64, 32, 16, 8)), tuple()):
    if t in (operand1, operand2):
      return t
  raise util.SemanticError('cannot parse type: %s %s %s' %
                           (operand1, operator, operand2))


def get_max_val(node) -> int:
  """Return the maximum valid value of an integer type."""
  if is_const(node):
    return int(node.num)
  haoda_type = node.haoda_type
  if haoda_type.is_float:
    raise TypeError('haoda_type has to be an integer type, got %s' % haoda_type)
  if haoda_type.is_fixed:
    raise NotImplementedError
  if haoda_type.startswith('uint'):
    return 2**haoda_type.width_in_bits - 1
  return 2**(haoda_type.width_in_bits - 1) - 1


def get_min_val(node) -> int:
  """Return the minimum valid value of an integer type."""
  if is_const(node):
    return int(node.num)
  haoda_type = node.haoda_type
  if haoda_type.is_float:
    raise TypeError('haoda_type has to be an integer type, got %s' % haoda_type)
  if haoda_type.is_fixed:
    raise NotImplementedError
  if haoda_type.startswith('uint'):
    return 0
  return -2**(haoda_type.width_in_bits - 1)


REDUCTION_OPS = {'+': AddSub, '*': MulDiv}
REDUCTION_FUNCS = {'min', 'max'}


def to_reduction(node: Node) -> Optional[Tuple[str, Tuple[Node, ...]]]:
  """Extract reduction expression from a Node.

  Args:
    node: Node to extract.

  Returns:
    None if node is not a reduction expression, tuple of (operator, operands)
    otherwise. operator is a string representing the reduction operator.
    operands is a tuple of operands as Nodes.
  """
  if isinstance(node, BinaryOp):
    operator = getattr(node, 'operator')
    if len(set(operator)) == 1 and operator[0] in REDUCTION_OPS:
      return operator[0], getattr(node, 'operand')
  elif isinstance(node, Call):
    operator = getattr(node, 'name')
    if operator in REDUCTION_FUNCS:
      return operator, getattr(node, 'arg')
  return None


def from_reduction(operator: str, operands: Tuple[Node, ...]) -> Node:
  """Assemble Node from a reduction expression.

  Args:
    operator: String representing the reduction operator.
    operands: Tuple of Nodes.

  Returns:
    Assembled Node.

  Raises:
    ValueError if operator is not a reduction operator.
  """
  if operator in REDUCTION_OPS:
    return REDUCTION_OPS[operator](operator=(operator,) * (len(operands) - 1),
                                   operand=operands)
  if operator in {'min', 'max'}:
    return Call(name=operator, arg=operands)
  raise ValueError('%s is not a reduction operator' % operator)
