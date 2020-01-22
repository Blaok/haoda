import unittest

from haoda import ir


class TestIr(unittest.TestCase):

  def setUp(self):
    self.ref = ir.Ref(name='foo', idx=(0, 23), lat=None)
    self.expr_ref = ir.Ref(name='bar', idx=(233, 42), lat=None)
    self.int8 = ir.Type('int8')
    self.expr_ref.haoda_type = self.int8
    self.expr = ir.Expr(operand=(self.expr_ref,), operator=())
    self.let_ref = ir.Ref(name='bar_l', idx=(42, 2333), lat=None)
    self.let_expr = ir.Expr(operand=(self.let_ref,), operator=())
    self.let = ir.Let(haoda_type=self.int8, name='foo_l', expr=self.let_expr)
    self.let_ref2 = ir.Ref(name='bar_l2', idx=(0, 42), lat=None)
    self.let_expr2 = ir.Expr(operand=(self.let_ref2,), operator=())
    self.let2 = ir.Let(haoda_type=self.int8, name='foo_l2', expr=self.let_expr2)

  def test_let(self):
    self.assertEqual(
        str(ir.Let(haoda_type=self.int8, name='foo', expr=self.expr)),
        'int8 foo = bar(233, 42)')
    self.assertEqual(str(ir.Let(haoda_type=None, name='foo', expr=self.expr)),
                     'int8 foo = bar(233, 42)')

  def test_ref(self):
    self.assertEqual(str(ir.Ref(name='foo', idx=[0], lat=None)), 'foo(0)')
    self.assertEqual(str(ir.Ref(name='foo', idx=[0], lat=233)), 'foo(0) ~233')
    self.assertEqual(str(ir.Ref(name='foo', idx=[0, 23], lat=233)),
                     'foo(0, 23) ~233')

  def test_binary_operations(self):
    for operand, operators in [(ir.Expr, ('||',)), (ir.LogicAnd, ('&&',)),
                               (ir.BinaryOr, ('|',)), (ir.Xor, ('^',)),
                               (ir.BinaryAnd, ('&',)), (ir.EqCmp, ('==', '!=')),
                               (ir.LtCmp, ('<=', '>=', '<', '>')),
                               (ir.AddSub, ('+', '-')),
                               (ir.MulDiv, ('*', '/', '%'))]:
      self.assertEqual(
          str(
              operand(operand=['op%d' % x for x in range(len(operators) + 1)],
                      operator=operators)),
          '(op0' + ''.join(' {} op{}'.format(op, idx + 1)
                           for idx, op in enumerate(operators)) + ')')

  def test_unary(self):
    self.assertEqual(str(ir.Unary(operator='+-~!'.split(), operand='op')),
                     '+-~!op')

  def test_cast(self):
    self.assertEqual(str(ir.Cast(haoda_type=self.int8, expr='expr')),
                     'int8(expr)')

  def test_call(self):
    self.assertEqual(str(ir.Call(name='pi', arg=[])), 'pi()')
    self.assertEqual(str(ir.Call(name='sqrt', arg=['arg'])), 'sqrt(arg)')
    self.assertEqual(
        str(ir.Call(name='select', arg=['condition', 'true_val', 'false_val'])),
        'select(condition, true_val, false_val)')

  def test_var(self):
    self.assertEqual(str(ir.Var(name='foo', idx=[])), 'foo')
    self.assertEqual(str(ir.Var(name='foo', idx=[0])), 'foo[0]')
    self.assertEqual(str(ir.Var(name='foo', idx=[0, 1])), 'foo[0][1]')
