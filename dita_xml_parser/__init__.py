"""Convenience exports for the ``dita_xml_parser`` package.

The package mainly exposes :class:`Dita2LLM` which implements the
transformation workflow used in the tests.  Keeping the import in this module
allows ``from dita_xml_parser import Dita2LLM`` to work for novice users.
"""

from .transformer import Dita2LLM

__all__ = ["Dita2LLM"]
