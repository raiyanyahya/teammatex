"""Compatibility re-export of the ``PR`` model.

``PR`` is defined in :mod:`app.models.task`, alongside ``Task``: the two models
reference each other's type in their relationships, and keeping them in separate
modules forced a module-level import cycle. Importing ``PR`` from here still works
for existing call sites.
"""

from app.models.task import PR

__all__ = ["PR"]
