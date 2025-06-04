"""Configuration for ``dita_xml_parser``.

The constants defined here are intentionally simple.  Keeping configuration in
a dedicated module allows new developers to quickly understand what can be
tweaked without digging through the main code base.
"""

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
