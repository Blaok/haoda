import collections

import sys
import enum
from typing import Dict, NamedTuple, Optional, TextIO, List, Tuple
import logging

from haoda import util

__all__ = (
    'parse_hierarchical_utilization_report',
    'HierarchicalUtilization',
)

_logger = logging.getLogger().getChild(__name__)


class HierarchicalUtilization:
  """Semantic-agnostic hierarchical utilization."""
  device: str
  parent: Optional['HierarchicalUtilization']
  children: List['HierarchicalUtilization']
  instance: str
  schema: Dict[str, int]
  items: Tuple[str, ...]

  def __init__(
      self,
      device: str,
      instance: str,
      schema: Dict[str, int],
      items: Tuple[str, ...],
      parent: Optional['HierarchicalUtilization'] = None,
  ) -> None:
    if len(schema) != len(items):
      raise TypeError('mismatching schema and items')
    self.device = device
    self.parent = parent
    self.children = []
    if parent is not None:
      parent.children.append(self)
    self.instance = instance
    self.schema = schema
    self.items = items

  def __getitem__(self, key: str) -> str:
    return self.items[self.schema[key]]

  def __str__(self) -> str:
    parent = None
    if self.parent is not None:
      parent = self.parent.instance
    return '\n'.join((
        '',
        f'instance: {self.instance}',
        f'parent: {parent}',
        *(f'{key}: {value}' for key, value in zip(self.schema, self.items)),
    ))


def parse_hierarchical_utilization_report(
    rpt_file: TextIO) -> HierarchicalUtilization:
  """Parse hierarchical utilization report.

  This is a compromise where Vivado won't export structured report from scripts.
 """

  class ParseState(enum.Enum):
    PROLOG = 0
    HEADER = 1
    BODY = 2
    EPILOG = 3

  parse_state = ParseState.PROLOG
  stack: List[HierarchicalUtilization] = []
  device = ''

  for line in rpt_file:
    line = line.strip()
    items = line.split()
    if len(items) == 4 and items[:3] == ['|', 'Device', ':']:
      device = items[3]
      continue
    if set(line) == {'+', '-'}:
      if parse_state == ParseState.PROLOG:
        parse_state = ParseState.HEADER
      elif parse_state == ParseState.HEADER:
        parse_state = ParseState.BODY
      elif parse_state == ParseState.BODY:
        parse_state = ParseState.EPILOG
      else:
        raise util.InputError('unexpected table separator line')
      continue

    if parse_state == ParseState.HEADER:
      instance, items = get_items(line)
      assert instance.lstrip() == 'Instance'
      schema = {x.lstrip(): i for i, x in enumerate(items)}

    elif parse_state == ParseState.BODY:
      instance, items = get_items(line)
      while (len(instance) - len(instance.lstrip(' '))) // 2 < len(stack):
        stack.pop()
      instance = instance.lstrip()
      parent = stack[-1] if stack else None
      stack.append(
          HierarchicalUtilization(device, instance, schema, items, parent))

  return stack[0]


def get_items(line: str) -> Tuple[str, Tuple[str, ...]]:
  """Split a table line into items.

  Args:
      line (str): A line in a report table.

  Returns:
      Tuple[str, ...]: Fields splitted by '|' with blank on the right stripped.
  """
  items = line.strip().strip('|').split('|')
  return items[0].rstrip(), tuple(x.strip() for x in items[1:])
