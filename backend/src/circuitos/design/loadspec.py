"""How the user specifies the load of a rectifier: by its power or by its mean current."""

from __future__ import annotations

from typing import Literal

LoadBy = Literal["potencia", "corrente"]
