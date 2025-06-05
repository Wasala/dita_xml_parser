"""Validation utilities for DITA XML files."""

from __future__ import annotations

import logging
import os
from typing import List

from lxml import etree

import config
from . import utils


class ValidationReport:
    """Simple container for validation results."""

    def __init__(self, passed: bool, details: List[str]):
        self.passed = passed
        self.details = details


class DitaValidator:
    """Validate translated XML against the source structure."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def validate(
        self,
        src_xml: str,
        tgt_xml: str,
        skeleton_dir: str | None = None,
    ) -> ValidationReport:
        """Validate that ``tgt_xml`` matches ``src_xml`` structure."""
        self.logger.info("Start validate: %s vs %s", src_xml, tgt_xml)

        if not os.path.exists(src_xml):
            msg = f"Source XML not found: {src_xml}"
            self.logger.error(msg)
            return ValidationReport(False, [msg])
        if not os.path.exists(tgt_xml):
            msg = f"Target XML not found: {tgt_xml}"
            self.logger.error(msg)
            return ValidationReport(False, [msg])

        parser = etree.XMLParser(remove_blank_text=False)
        try:
            src_tree = etree.parse(src_xml, parser)
            tgt_tree = etree.parse(tgt_xml, parser)
        except Exception as exc:  # pragma: no cover - unexpected parse error
            self.logger.error("Validation parse error: %s", exc)
            return ValidationReport(False, [str(exc)])

        errors: List[str] = []
        warnings: List[str] = []

        if src_tree.docinfo.doctype != tgt_tree.docinfo.doctype:
            errors.append("DOCTYPE changed")

        def walk(e1: etree._Element, e2: etree._Element, path: str = "") -> None:
            if isinstance(e1.tag, str) and isinstance(e2.tag, str):
                if e1.tag != e2.tag:
                    errors.append(f"tag mismatch at {path}/{e1.tag}")
                    return
                if e1.attrib != e2.attrib:
                    errors.append(f"attrib mismatch at {path}/{e1.tag}")
                children1 = list(e1)
                children2 = list(e2)
                if len(children1) != len(children2):
                    errors.append(f"child count mismatch at {path}/{e1.tag}")
                for c1, c2 in zip(children1, children2):
                    walk(c1, c2, path + "/" + e1.tag)
            elif isinstance(e1, etree._Comment) and isinstance(e2, etree._Comment):
                if e1.text != e2.text:
                    errors.append(f"comment mismatch at {path}")
            elif isinstance(e1, etree._ProcessingInstruction) and isinstance(
                e2, etree._ProcessingInstruction
            ):
                if e1.target != e2.target or e1.text != e2.text:
                    errors.append(f"pi mismatch at {path}")

        walk(src_tree.getroot(), tgt_tree.getroot())

        base = os.path.splitext(os.path.basename(src_xml))[0]
        skel_dir = skeleton_dir or os.path.dirname(tgt_xml)
        skeleton_path = os.path.join(skel_dir, f"{base}.skeleton.xml")
        if os.path.exists(skeleton_path):
            skel_tree = etree.parse(skeleton_path, parser)
            skel_et = etree.ElementTree(skel_tree.getroot())
            for seg_elem in skel_tree.xpath("//*[@data-dita-seg-id]"):
                seg_id = seg_elem.get("data-dita-seg-id")
                xpath = skel_et.getpath(seg_elem)
                src_match = src_tree.xpath(xpath)
                tgt_match = tgt_tree.xpath(xpath)
                if src_match and tgt_match:
                    s_inner = utils.get_inner_xml(src_match[0]).strip()
                    t_inner = utils.get_inner_xml(tgt_match[0]).strip()
                    if s_inner == t_inner and s_inner:
                        msg = f"Untranslated segment {seg_id} at {xpath}"
                        warnings.append(msg)
                        self.logger.warning(msg)

        passed = not errors
        for err in errors:
            self.logger.error(err)
        for warn in warnings:
            self.logger.warning(warn)
        self.logger.info("End validate")
        return ValidationReport(passed, errors + warnings)

