"""Functions for generating simplified placeholder XML versions."""

from __future__ import annotations

import copy
import os
from typing import Dict

from lxml import etree

import config


def write_minimal(tree: etree._ElementTree, base: str, intermediate_dir: str, encoding: str, logger) -> None:
    """Create a minimal placeholder version of ``tree`` for the LLM."""
    minimal = copy.deepcopy(tree)

    for el in minimal.xpath("//comment()"):
        el.getparent().remove(el)
    for el in minimal.xpath("//processing-instruction()"):
        el.getparent().remove(el)

    placeholder_map: Dict[str, str] = {}
    tag_to_placeholder: Dict[str, str] = {}
    counter = 1
    for elem in minimal.iter():
        if elem.tag in tag_to_placeholder:
            placeholder = tag_to_placeholder[elem.tag]
        else:
            placeholder = f"t{counter}"
            tag_to_placeholder[elem.tag] = placeholder
            placeholder_map[placeholder] = elem.tag
            counter += 1
        new_tag = placeholder
        seg_id = elem.get("data-dita-seg-id")
        for attr in list(elem.attrib):
            del elem.attrib[attr]
        if seg_id:
            new_tag = f"{placeholder}_{seg_id}"
        elem.tag = new_tag

    minimal_path = os.path.join(intermediate_dir, f"{base}.minimal.xml")
    minimal_tree = etree.ElementTree(minimal.getroot())
    minimal_tree.write(minimal_path, encoding=encoding, xml_declaration=False, pretty_print=True)

    mapping_path = os.path.join(intermediate_dir, f"{base}.tag_mappings.txt")
    with open(mapping_path, "w", encoding="utf-8") as f:
        for placeholder, original in placeholder_map.items():
            f.write(f"{placeholder} -> {original}\n")

    logger.info("Minimal XML tags generated: %s", counter - 1)
    logger.info("Minimal XML path: %s", minimal_path)
    logger.info("Mapping path: %s", mapping_path)
