"""Transformation utilities for preparing DITA XML for LLM translation."""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import List, Tuple


from lxml import etree

import config
from . import minimal
from . import utils


class ValidationReport:
    """Simple container for validation results."""

    def __init__(self, passed: bool, details: List[str]) -> None:
        self.passed = passed
        self.details = details


class Dita2LLM:
    """Coordinate parsing and reintegration of DITA XML files."""

    def __init__(
        self,
        source_dir: str | None = None,
        intermediate_dir: str | None = None,
        target_dir: str | None = None,
        source_lang: str = "en-US",
        target_lang: str = "de-DE",
        log_dir: str = "logs",
    ) -> None:
        self.source_dir = source_dir
        self.intermediate_dir = intermediate_dir
        self.target_dir = target_dir
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.log_dir = log_dir
        if self.intermediate_dir:
            os.makedirs(self.intermediate_dir, exist_ok=True)
        if self.target_dir:
            os.makedirs(self.target_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        self.logger = logging.getLogger("Dita2LLM")
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL))
        # Path to the most recently generated target file
        self._last_target_path: str | None = None

    # Utility functions
    def _init_log(self, xml_path: str) -> str:
        """Start a fresh log file for the given XML path."""

        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        base = os.path.splitext(os.path.basename(xml_path))[0]
        log_path = os.path.join(self.log_dir, f"{base}_{ts}.log")
        fh = logging.FileHandler(log_path)
        formatter = logging.Formatter("%(asctime)s %(levelname)s:%(message)s")
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        return log_path

    def _resolve(self, path: str, base: str | None) -> str:
        """Return ``path`` joined with ``base`` if it lacks directory info."""

        if os.path.isabs(path) or os.path.dirname(path):
            return path
        if base:
            return os.path.join(base, path)
        return path

    def parse(
        self,
        xml_path: str,
        skeleton_path: str | None = None,
        segments_path: str | None = None,
    ) -> Tuple[List[dict], str]:
        """Parse ``xml_path`` and produce JSON segments and a skeleton XML."""

        xml_path = self._resolve(xml_path, self.source_dir)
        self._init_log(xml_path)
        self.logger.info("Start parse: %s", xml_path)
        with open(xml_path, "rb") as f:
            header = f.read(200).decode("ascii", errors="ignore")
        encoding = "utf-8"
        if "encoding" in header:
            import re

            match = re.search(r"encoding=[\"']([^\"']+)[\"']", header)
            if match:
                encoding = match.group(1)
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(xml_path, parser)
        root = tree.getroot()
        ids: List[Tuple[etree._Element, str]] = []
        count = 0
        for elem in root.iter():
            if utils.is_container(elem):
                if "data-dita-seg-id" not in elem.attrib:
                    seg_id = utils.generate_id()
                    elem.set("data-dita-seg-id", seg_id)
                else:
                    seg_id = elem.get("data-dita-seg-id")
                ids.append((elem, seg_id))
                count += 1
        base = os.path.splitext(os.path.basename(xml_path))[0]
        base_dir = self.intermediate_dir or os.path.dirname(skeleton_path or xml_path) or "."
        if skeleton_path is None:
            skeleton_path = os.path.join(base_dir, f"{base}.skeleton.xml")
        tree.write(
            skeleton_path,
            encoding=encoding,
            xml_declaration=True,
            doctype=tree.docinfo.doctype,
        )
        segments = []
        for elem, seg_id in ids:
            segments.append({"id": seg_id, self.source_lang: utils.get_inner_xml(elem)})
        if segments_path is None:
            segments_path = os.path.join(base_dir, f"{base}.{self.source_lang}_segments.json")
        with open(segments_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        minimal.write_minimal(tree, base, base_dir, encoding, self.logger)
        self.logger.info("Containers found: %s", count)
        self.logger.info("JSON segments written: %s", len(segments))
        self.logger.info("Skeleton path: %s", skeleton_path)
        self.logger.info("Segments path: %s", segments_path)
        self.logger.info("End parse")
        return segments, skeleton_path

    def integrate(
        self,
        translation_json_path: str,
        skeleton_path: str | None = None,
        output_path: str | None = None,
    ) -> str:
        """Merge translated segments back into the skeleton XML."""

        translation_json_path = self._resolve(translation_json_path, self.intermediate_dir)
        self.logger.info("Start integrate: %s", translation_json_path)
        with open(translation_json_path, "r", encoding="utf-8") as f:
            translations = json.load(f)
        if isinstance(translations, dict):
            translations = [translations]
        # Determine base name
        name = os.path.splitext(os.path.basename(translation_json_path))[0]
        if name.endswith(f".{self.target_lang}_translated"):
            base = name[: -(len(self.target_lang) + 12)]
        else:
            base = name.split(".")[0]
        if skeleton_path is None:
            skel_base = self.intermediate_dir or os.path.dirname(translation_json_path)
            skeleton_path = os.path.join(skel_base, f"{base}.skeleton.xml")
        else:
            skeleton_path = self._resolve(skeleton_path, self.intermediate_dir)
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(skeleton_path, parser)
        root = tree.getroot()
        for idx, entry in enumerate(translations, start=1):
            if "id" in entry:
                seg_id = entry["id"]
                value = entry.get(self.target_lang) or next(
                    (v for k, v in entry.items() if k != "id"), ""
                )
            else:
                seg_id, value = next(iter(entry.items()))
            elems = root.xpath(f"//*[@data-dita-seg-id='{seg_id}']")
            if not elems:
                self.logger.error(f"ID {seg_id} not found in skeleton")
                continue
            elem = elems[0]
            utils.set_inner_xml(elem, value)
        # remove helper attributes before saving
        for el in root.iter():
            if "data-dita-seg-id" in el.attrib:
                del el.attrib["data-dita-seg-id"]
        if output_path is None:
            out_base = self.target_dir or os.path.dirname(skeleton_path)
            target_path = os.path.join(out_base, f"{base}.xml")
        else:
            target_path = self._resolve(output_path, self.target_dir)
        tree.write(
            target_path,
            encoding="utf-8",
            xml_declaration=True,
            doctype=tree.docinfo.doctype,
            pretty_print=True,
        )
        self._last_target_path = target_path
        self.logger.info(f"Skeleton used: {skeleton_path}")
        self.logger.info(f"Wrote integrated file: {target_path}")
        self.logger.info("End integrate")
        return target_path

    def validate(self, src_xml: str, tgt_xml: str) -> ValidationReport:
        """Check that ``tgt_xml`` still structurally matches ``src_xml``."""

        src_xml = self._resolve(src_xml, self.source_dir)
        tgt_xml = self._resolve(tgt_xml, self.target_dir)
        self.logger.info("Start validate: %s vs %s", src_xml, tgt_xml)
        parser = etree.XMLParser(remove_blank_text=False)
        try:
            src_tree = etree.parse(src_xml, parser)
            tgt_tree = etree.parse(tgt_xml, parser)
        except Exception as e:
            self.logger.error(f"Validation parse error: {e}")
            return ValidationReport(False, [str(e)])
        errors = []
        if src_tree.docinfo.doctype != tgt_tree.docinfo.doctype:
            errors.append("DOCTYPE changed")

        def walk(e1, e2, path=""):
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
        passed = not errors
        for err in errors:
            self.logger.error(err)
        self.logger.info("End validate")
        return ValidationReport(passed, errors)

    def generate_dummy_translation(self, segments_json_path: str, output_path: str) -> str:
        segments_json_path = self._resolve(segments_json_path, self.intermediate_dir)
        output_path = self._resolve(output_path, self.intermediate_dir)
        with open(segments_json_path, "r", encoding="utf-8") as f:
            segments = json.load(f)
        translations = []
        for idx, seg in enumerate(segments, start=1):
            prefix = f"[{self.target_lang}_{idx}] "
            translations.append(
                {
                    "id": seg["id"],
                    self.target_lang: prefix + seg[self.source_lang],
                }
            )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(translations, f, indent=2, ensure_ascii=False)
        self.logger.info(f"Dummy translation written: {output_path}")
        return output_path

    def integrate_from_simple_xml(self, simple_xml_path: str) -> Tuple[str, ValidationReport]:
        """Integrate translations from a translated minimal XML file.

        The provided ``simple_xml_path`` should point to a minimal XML where the
        element names are placeholder tags generated by :meth:`parse` and the
        textual content has been translated. Segmentation identifiers are
        encoded in the tag name after an underscore.  This method reconstructs
        the original XML structure using the mapping and skeleton created during
        parsing, integrates the translated text, and validates the final file
        against the source XML.

        Parameters
        ----------
        simple_xml_path: str
            Path to the translated minimal XML file.

        Returns
        -------
        Tuple[str, ValidationReport]
            Path to the generated translated XML and the validation report.
        """
        simple_xml_path = self._resolve(simple_xml_path, self.intermediate_dir)
        self.logger.info(f"Start integrate from simple XML: {simple_xml_path}")

        name = os.path.splitext(os.path.basename(simple_xml_path))[0]
        if ".minimal" in name:
            base = name.split(".minimal")[0]
        else:
            base = name

        base_dir = self.intermediate_dir or os.path.dirname(simple_xml_path)
        mapping_path = os.path.join(base_dir, f"{base}.tag_mappings.txt")
        skeleton_path = os.path.join(base_dir, f"{base}.skeleton.xml")
        src_base = self.source_dir or os.path.dirname(simple_xml_path)
        source_xml_path = os.path.join(src_base, f"{base}.xml")

        parser = etree.XMLParser(remove_blank_text=False)
        simple_tree = etree.parse(simple_xml_path, parser)

        mappings: Dict[str, str] = {}
        with open(mapping_path, "r", encoding="utf-8") as f:
            for line in f:
                if "->" in line:
                    ph, tag = line.strip().split(" -> ")
                    mappings[ph] = tag

        # Replace placeholder tags with real tag names and capture seg ids
        for elem in simple_tree.getroot().iter():
            tag = elem.tag
            seg_id = None
            if "_" in tag:
                placeholder, seg_id = tag.split("_", 1)
            else:
                placeholder = tag
            elem.tag = mappings.get(placeholder, placeholder)
            if seg_id:
                elem.set("data-dita-seg-id", seg_id)

        skeleton_tree = etree.parse(skeleton_path, parser)
        skeleton_root = skeleton_tree.getroot()

        def copy_attrs(src: etree._Element, dst: etree._Element):
            for k, v in dst.attrib.items():
                if k not in src.attrib:
                    src.set(k, v)

        def merge(trans_elem: etree._Element, skel_elem: etree._Element):
            copy_attrs(trans_elem, skel_elem)
            skel_elem.text = trans_elem.text
            used: List[etree._Element] = []
            for s_child in skel_elem:
                match = None
                sid = s_child.get("data-dita-seg-id")
                if sid:
                    for c in trans_elem.xpath(f"*[@data-dita-seg-id='{sid}']"):
                        match = c
                        break
                else:
                    for c in trans_elem:
                        if c.tag == s_child.tag and c not in used:
                            match = c
                            used.append(c)
                            break
                if match is not None:
                    merge(match, s_child)
                    s_child.tail = match.tail

        for seg_elem in simple_tree.getroot().xpath("//*[@data-dita-seg-id]"):
            seg_id = seg_elem.get("data-dita-seg-id")
            match = skeleton_root.xpath(f"//*[@data-dita-seg-id='{seg_id}']")
            if match:
                merge(seg_elem, match[0])

        for el in skeleton_root.iter():
            if "data-dita-seg-id" in el.attrib:
                del el.attrib["data-dita-seg-id"]

        out_base = self.target_dir or base_dir
        target_path = os.path.join(out_base, f"{base}.xml")
        skeleton_tree.write(
            target_path,
            encoding="utf-8",
            xml_declaration=True,
            doctype=skeleton_tree.docinfo.doctype,
            pretty_print=True,
        )
        self._last_target_path = target_path
        report = self.validate(source_xml_path, target_path)
        self.logger.info("End integrate from simple XML")
        return target_path, report
