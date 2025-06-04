"""Utility helpers for working with DITA XML trees."""

from __future__ import annotations

from secrets import token_hex
from typing import List

from lxml import etree

import config


def generate_id(length: int = config.ID_LENGTH) -> str:
    """Return a random hexadecimal identifier with ``length`` digits."""
    return token_hex(length // 2)


def has_inline_child(elem: etree._Element) -> bool:
    """Return ``True`` if ``elem`` contains any inline child elements."""
    return any(child.tag in config.INLINE_TAGS for child in elem)


def is_container(elem: etree._Element) -> bool:
    """Return ``True`` if ``elem`` is considered a translatable block."""
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
    """Return the inner XML of ``elem`` without the outer tag."""
    parts: List[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(etree.tostring(child, encoding=str))
    return "".join(parts)


def set_inner_xml(elem: etree._Element, xml_string: str) -> None:
    """Replace the children of ``elem`` with the parsed ``xml_string``."""
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
