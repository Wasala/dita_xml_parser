"""Creation of light-weight XML files for machine translation.

The ``write_minimal`` utility strips comments and processing instructions and
replaces real tag names with short placeholders.  The intent is to reduce the
size and vocabulary of the XML so that LLM based translators see only the text
content with minimal structural noise.  Mapping information is written out so
that placeholders can later be restored to their original names.
"""

from __future__ import annotations

import copy
import os
from typing import Dict

from lxml import etree



def write_minimal(
    tree: etree._ElementTree,
    base: str,
    intermediate_dir: str,
    encoding: str,
    logger,
) -> None:
    """Write a simplified XML copy for translation.

    The goal is to feed a smaller and more uniform document to large language
    models.  Every tag is replaced with a numbered placeholder so the resulting
    file contains only the text to be translated and minimal structural cues.
    This reduces prompt size and encourages consistent handling of repeated
    tags.  A mapping is stored alongside the minimal file so that placeholders
    can be restored after translation.

    :param tree: Parsed source XML tree.
    :param base: Base filename used when writing output files.
    :param intermediate_dir: Directory for temporary artifacts.
    :param encoding: Encoding used when serializing XML.
    :param logger: Logger for progress messages.
    :returns: ``None``. Files are written for later stages.
    """
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
