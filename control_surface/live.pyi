import typing

from ableton.v2.base import Slot as __Slot

T = typing.TypeVar("T")

def find_if(
    predicate: typing.Callable[[T], typing.Any], seq: typing.Iterable[T]
) -> typing.Optional[T]: ...
def flatten(list: typing.Iterable[typing.Iterable[T]]) -> typing.Iterable[T]: ...

class lazy_attribute(typing.Generic[T]):
    def __init__(self, func: typing.Callable[[typing.Any], T], name=...) -> None: ...
    def __get__(self, obj, cls=...) -> T: ...

def listens(
    event_path: str, *a, **k
) -> typing.Callable[
    [typing.Callable[[typing.Any, typing.Any], typing.Any]], __Slot
]: ...
def memoize(function: typing.Callable[..., T]) -> typing.Callable[..., T]: ...
