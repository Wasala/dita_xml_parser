"""Check translated XML files against the source.

Validation is kept separate from transformation so that alternate translation
pipelines can still reuse the logic.  Only a lightweight dependency on
:mod:`lxml` is required which keeps the validator usable in restricted
environments.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

from lxml import etree

from . import utils


@dataclass
class ValidationReport:
    """Simple result object for :class:`DitaValidator`.

    Storing the pass/fail boolean along with detail messages keeps the
    interface minimal while still allowing callers to inspect warnings and
    errors.  The dataclass representation is easy to serialize for logging or
    further automated analysis.
    """

    passed: bool
    details: List[str]

    def __repr__(self) -> str:
        return f"ValidationReport(passed={self.passed}, details={self.details})"


class DitaValidator:
    """Validate translated XML against the source structure.

    The validator focuses purely on structural fidelity: tags, attributes and
    ordering must remain unchanged compared to the source skeleton.  Content
    differences are ignored except when checking for untranslated segments.  By
    isolating validation in its own class, the :class:`Dita2LLM` workflow can be
    reused with custom validators or extended rules.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def set_logger(self, logger: logging.Logger) -> None:
        """Swap out the logger used for reporting.

        Injecting a custom logger allows host applications to integrate the
        validator with their own logging setup or testing harness.  No return
        value is provided to keep the call site simple.

        :param logger: The logger instance to use.
        """

        self.logger = logger

    def _parse_tree(
        self, xml_path: str, parser: etree.XMLParser
    ) -> etree._ElementTree | None:
        """Parse an XML file with graceful error handling.

        The validator reuses this helper for both source and target documents
        so that any syntax issues are reported consistently.  Returning ``None``
        instead of raising allows the caller to produce a single validation
        report even when one of the files fails to parse.

        :param xml_path: Path to the XML file on disk.
        :param parser: Configured XML parser instance.
        :returns: The parsed element tree or ``None`` on failure.
        """

        try:
            return etree.parse(xml_path, parser)
        except (OSError, etree.XMLSyntaxError) as exc:  # pragma: no cover - unexpected
            self.logger.error("Validation parse error: %s", exc)
            return None

    def _collect_untranslated(
        self,
        src_tree: etree._ElementTree,
        tgt_tree: etree._ElementTree,
        skeleton_path: str,
    ) -> List[str]:
        """Detect segments that were not translated.

        By comparing the inner XML of source and target at locations identified
        via the skeleton, this helper can flag untranslated text while ignoring
        structural differences.  The check is optional when no skeleton is
        available and results in a list of warning strings rather than errors.

        :param src_tree: Parsed source XML tree.
        :param tgt_tree: Parsed translated XML tree.
        :param skeleton_path: Path to the skeleton XML produced during parsing.
        :returns: A list of human readable warning messages.
        """

        warnings: List[str] = []
        if os.path.exists(skeleton_path):
            skel_tree = etree.parse(skeleton_path, etree.XMLParser(remove_blank_text=False))
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
        return warnings

    def validate(
        self,
        src_xml: str,
        tgt_xml: str,
        skeleton_dir: str | None = None,
    ) -> ValidationReport:
        """Check structural fidelity of a translated file.

        The method loads both source and target XML using the same parser to
        eliminate differences from whitespace handling.  It then walks the tree
        comparing tag names and attributes, reporting mismatches as errors.
        When a skeleton is available, untranslated segments are flagged as
        warnings.  The result is returned as a :class:`ValidationReport` rather
        than raising so that callers can decide how strict to be.

        :param src_xml: Path to the original XML document.
        :param tgt_xml: Path to the translated XML document.
        :param skeleton_dir: Directory containing the skeleton from ``parse``.
        :returns: Object with ``passed`` boolean and message list.
        """
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
        src_tree = self._parse_tree(src_xml, parser)
        tgt_tree = self._parse_tree(tgt_xml, parser)
        if src_tree is None or tgt_tree is None:
            return ValidationReport(False, ["Parse error"])

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
        warnings.extend(self._collect_untranslated(src_tree, tgt_tree, skeleton_path))

        passed = not errors
        for err in errors:
            self.logger.error(err)
        for warn in warnings:
            self.logger.warning(warn)
        self.logger.info("End validate")
        return ValidationReport(passed, errors + warnings)
