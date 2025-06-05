"""Small utilities used across the parser.

These helpers were intentionally kept independent of any class to make them
easy to test in isolation and to allow reuse in external scripts.  They deal
with low level XML manipulation that is repeated in several modules.
"""

from __future__ import annotations

from secrets import token_hex
from typing import List

from lxml import etree

import config


def generate_id(length: int = config.ID_LENGTH) -> str:
    """Generate a random identifier for segmentation.

    The IDs are short hexadecimal strings to keep XML attributes compact while
    still providing enough entropy for temporary uniqueness.  The length is
    configurable so integrators can trade readability for collision risk.

    :param length: Desired number of hex characters.
    :returns: A random string of ``length`` hexadecimal digits.
    """
    return token_hex(length // 2)


def has_inline_child(elem: etree._Element) -> bool:
    """Check for inline elements within a container.

    Inline tags are listed in :mod:`config` and represent elements that should
    not trigger segmentation on their own.  This helper is used during parsing
    to decide whether a container has mixed content that may require splitting.

    :param elem: Element to inspect.
    :returns: ``True`` if an inline child is present.
    """
    return any(child.tag in config.INLINE_TAGS for child in elem)


def is_container(elem: etree._Element) -> bool:
    """Determine if an element should be translated as a unit.

    The heuristic treats elements with textual content or inline children as
    translation containers.  Inline-only tags are ignored to avoid segmenting
    inside emphasis or hyperlink elements.  This keeps translation segments
    stable even when authors rearrange formatting.

    :param elem: Element to evaluate.
    :returns: ``True`` if the element is a translation container.
    """
    if elem.tag in config.INLINE_TAGS:
        return False
    if elem.text and elem.text.strip():
        return True
    for child in elem:
        tail_has_text = child.tail and child.tail.strip()
        if tail_has_text or child.tag in config.INLINE_TAGS:
            return True
    return False


def get_inner_xml(elem: etree._Element) -> str:
    """Extract the serialized content of an element.

    The caller can use this to capture text and child markup while dropping the
    container itself.  It avoids copying attribute data and keeps whitespace as
    authored in the source.

    :param elem: Element whose children should be serialized.
    :returns: Inner XML without the outer element.
    """
    parts: List[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(etree.tostring(child, encoding=str))
    return "".join(parts)


def set_inner_xml(elem: etree._Element, xml_string: str) -> None:
    """Replace an element's children with new markup.

    The helper parses the supplied ``xml_string`` inside a dummy wrapper and
    then moves the resulting nodes under ``elem``.  This avoids issues with
    multiple top-level elements and preserves any surrounding whitespace.
    When the string is not well formed XML it is used as literal text instead
    of raising an exception.

    :param elem: Element to modify in place.
    :param xml_string: Raw XML fragment to insert.
    :returns: ``None``.
    """
    for child in list(elem):
        elem.remove(child)
    elem.text = None
    wrapper = f"<wrapper>{xml_string}</wrapper>"
    try:
        frag = etree.fromstring(wrapper)
        elem.text = frag.text
        for child in frag:
            elem.append(child)
    except etree.XMLSyntaxError:
        elem.text = xml_string
