from typing import NamedTuple
import enum

__all__ = (
    'Cat',
    'Arg',
)


class Cat(enum.Enum):
  SCALAR = 0
  MMAP = 1
  ISTREAM = 2
  OSTREAM = 3


class Arg(NamedTuple):
  cat: Cat
  name: str  # name of the argument
  port: str  # name of the port to which the argument is connected to
  ctype: str
  width: int
