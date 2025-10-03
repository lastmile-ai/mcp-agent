"""
Helper utilities that are commonly used throughout the framework,
but which do not belong to any specific module.
"""

import functools
import json
from types import MethodType
from typing import Any, List, Callable, TypeVar

from pydantic import BaseModel

R = TypeVar("R")


def unwrap(c: Callable[..., Any]) -> Callable[..., Any]:
    """Return the underlying function object for any callable."""
    while True:
        if isinstance(c, functools.partial):
            c = c.func
        elif isinstance(c, MethodType):
            c = c.__func__
        else:
            return c


def typed_dict_extras(d: dict, exclude: List[str]):
    extras = {k: v for k, v in d.items() if k not in exclude}
    return extras


def to_string(obj: BaseModel | dict) -> str:
    """
    Convert a Pydantic model or dictionary to a JSON string.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump_json()
    else:
        return json.dumps(obj)


def ensure_serializable(data: BaseModel) -> BaseModel:
    """
    Workaround for https://github.com/pydantic/pydantic/issues/7713, see https://github.com/pydantic/pydantic/issues/7713#issuecomment-2604574418
    """
    try:
        json.dumps(data)
    except TypeError:
        # use `vars` to coerce nested data into dictionaries
        data_json_from_dicts = json.dumps(data, default=lambda x: vars(x))  # type: ignore
        data_obj = json.loads(data_json_from_dicts)
        data = type(data)(**data_obj)
    return data
