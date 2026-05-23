"""Shared Jinja2Templates instance with domain enums pre-registered as globals."""

import importlib
import inspect
import pkgutil
from enum import StrEnum
from pathlib import Path

from fastapi.templating import Jinja2Templates

import superhero_project.domain as _domain_pkg

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

for _mod_info in pkgutil.iter_modules(_domain_pkg.__path__):
    _mod = importlib.import_module(f"superhero_project.domain.{_mod_info.name}")
    for _name, _obj in inspect.getmembers(_mod, inspect.isclass):
        if issubclass(_obj, StrEnum) and _obj is not StrEnum:
            templates.env.globals[_name] = _obj
