"""Library configuration.

The parser is intentionally configurable via an external ``TOML`` file so
command line tools and interactive notebooks can alter defaults without
patching the code.  By reading ``DITA_PARSER_CONFIG`` first, deployments may
point to a central config location while still falling back to a project
``config.toml`` when the environment variable is unset.  The shipped constants
mirror the library's historic defaults for backward compatibility.
"""

from __future__ import annotations

import os
import pytoml

_CONFIG_PATH = os.environ.get(
    "DITA_PARSER_CONFIG",
    os.path.join(os.path.dirname(__file__), "config.toml"),
)

if os.path.exists(_CONFIG_PATH):
    with open(_CONFIG_PATH, "r", encoding="utf-8") as _cfg:
        _CONF = pytoml.load(_cfg)
else:
    _CONF = {}

INLINE_TAGS = {
    "b",
    "i",
    "u",
    "cite",
    "sub",
    "sup",
    "ph",
    "span",
    "xref",
    "tt",
    "code",
}

# Each translatable container gets a hex id of this length. Twelve digits give
# over a trillion possibilities which is enough for temporary identifiers.
ID_LENGTH: int = 12

# Default log level used by :class:`~dita_xml_parser.transformer.Dita2LLM`.
LOG_LEVEL: str = "INFO"

# Override with TOML values if provided
INLINE_TAGS = set(_CONF.get("INLINE_TAGS", INLINE_TAGS))
ID_LENGTH = int(_CONF.get("ID_LENGTH", ID_LENGTH))
LOG_LEVEL = _CONF.get("LOG_LEVEL", LOG_LEVEL)
