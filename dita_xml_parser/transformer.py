"""End-to-end helpers for translating DITA XML with LLMs.

This module contains the :class:`Dita2LLM` workflow which performs three main
steps: parsing source files, applying translations and validating the result.
It writes intermediate artifacts so the potentially expensive translation step
can be repeated or performed offline.  The design favors transparency and
modularity over raw speed, making it easier to debug and adapt to different
translation providers.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
from typing import Dict, List, Tuple


from lxml import etree

import config
from . import minimal
from . import utils
from .validator import DitaValidator, ValidationReport

DEFAULT_LOG_DIR = "logs"




class Dita2LLM:
    """High level workflow for XML translation.

    The class writes intermediate JSON and skeleton files so that translators
    can operate on small, self contained snippets.  Each step logs its actions
    to make troubleshooting easier.  Paths can be given relative to configured
    directories which simplifies testing and integration with other tools.
    """

    def __init__(
        self,
        source_dir: str | None = None,
        intermediate_dir: str | None = None,
        target_dir: str | None = None,
        languages: Tuple[str, str] = ("en-US", "de-DE"),
    ) -> None:
        self.source_dir = source_dir
        self.intermediate_dir = intermediate_dir
        self.target_dir = target_dir
        self.source_lang, self.target_lang = languages
        if self.intermediate_dir:
            os.makedirs(self.intermediate_dir, exist_ok=True)
        if self.target_dir:
            os.makedirs(self.target_dir, exist_ok=True)
        os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
        self.logger = logging.getLogger("Dita2LLM")
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL))
        self.validator = DitaValidator(self.logger)

    # Utility functions
    def _init_log(self, xml_path: str) -> str:
        """Create a dedicated log file for a processing run.

        Each XML file processed gets its own timestamped log.  This avoids
        interleaving messages from parallel runs and keeps troubleshooting
        focused on a single document.

        :param xml_path: Path of the XML file being processed.
        :returns: The full path to the created log file.
        """

        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        base = os.path.splitext(os.path.basename(xml_path))[0]
        log_path = os.path.join(DEFAULT_LOG_DIR, f"{base}_{ts}.log")
        fh = logging.FileHandler(log_path)
        formatter = logging.Formatter("%(asctime)s %(levelname)s:%(message)s")
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        return log_path

    def _ensure_log(self, xml_path: str) -> None:
        """Initialize logging when no file handler is active."""

        if not self.logger.handlers:
            self._init_log(xml_path)

    def _extract_dnt(self, root: etree._Element, mapping_path: str) -> None:
        """Replace configured elements with ``<dnt>`` placeholders."""

        mappings = {}
        targets = [e for e in root.iter() if e.tag in config.DO_NOT_TRANSLATE]
        for elem in targets:
            dnt_id = utils.generate_id()
            content = utils.get_inner_xml(elem)
            new = etree.Element("dnt")
            new.set("id", dnt_id)
            new.set("element", elem.tag)
            new.set("content", content)
            new.tail = elem.tail
            parent = elem.getparent()
            if parent is not None:
                parent.replace(elem, new)
            mappings[dnt_id] = {"element": elem.tag, "content": content}
        if mappings:
            with open(mapping_path, "w", encoding="utf-8") as f:
                json.dump(mappings, f, indent=2, ensure_ascii=False)
            self.logger.info("DNT mapping path: %s", mapping_path)
            self.logger.info("DNT elements replaced: %s", len(mappings))

    def _apply_translations(
        self, root: etree._Element, translations: List[dict]
    ) -> None:
        """Insert translated text back into the skeleton.

        The ``translations`` list is expected to contain dictionaries keyed by
        segment identifiers.  For robustness the method supports both
        ``{"id": "xyz", "de-DE": "..."}`` and ``{"xyz": "..."}`` styles.  Missing
        identifiers are logged but otherwise ignored so partial translations do
        not abort the workflow.

        :param root: Skeleton XML tree to modify.
        :param translations: Sequence of translation entries.
        :returns: ``None``.
        """

        for entry in translations:
            if "id" in entry:
                seg_id = entry["id"]
                value = entry.get(self.target_lang) or next(
                    (v for k, v in entry.items() if k != "id"), ""
                )
            else:
                seg_id, value = next(iter(entry.items()))
            elems = root.xpath(f"//*[@data-dita-seg-id='{seg_id}']")
            if not elems:
                self.logger.error("ID %s not found in skeleton", seg_id)
                continue
            utils.set_inner_xml(elems[0], value)

    def _remove_seg_ids(self, root: etree._Element) -> None:
        """Strip temporary segmentation IDs.

        After translations are applied the ``data-dita-seg-id`` attributes are
        no longer needed and might confuse downstream tooling.  The removal is
        done in-place on the provided tree.

        :param root: XML element whose descendants are cleaned.
        """

        for el in root.xpath("//*[@data-dita-seg-id]"):
            del el.attrib["data-dita-seg-id"]

    def _restore_dnt(self, root: etree._Element, mapping_path: str) -> None:
        """Replace ``<dnt>`` placeholders with the original elements."""

        if not os.path.exists(mapping_path):
            return
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        for dnt in root.xpath("//dnt[@id]"):
            dnt_id = dnt.get("id")
            orig = mapping.get(dnt_id, None)
            if orig is None:
                elem_name = dnt.get("element")
                content = dnt.get("content", "")
            else:
                elem_name = orig.get("element")
                content = orig.get("content", "")
            new_el = etree.Element(elem_name)
            utils.set_inner_xml(new_el, content)
            new_el.tail = dnt.tail
            parent = dnt.getparent()
            if parent is not None:
                parent.replace(dnt, new_el)

    def _load_mappings(self, path: str) -> Dict[str, str]:
        """Read the placeholder-to-tag mapping from disk.

        The mapping file is produced during :func:`minimal.write_minimal` and
        pairs each generated placeholder with the original element name.  It is
        a simple ``key -> value`` text format which keeps inspection easy.

        :param path: Location of the mapping file.
        :returns: Dictionary mapping placeholders to original tag names.
        """

        mappings: Dict[str, str] = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "->" in line:
                    ph, tag = line.strip().split(" -> ")
                    mappings[ph] = tag
        return mappings

    def _replace_placeholders(self, tree: etree._ElementTree, mappings: Dict[str, str]) -> None:
        """Restore original tag names in a minimal tree.

        During integration the minimal XML still uses placeholders.  This
        helper walks the tree and swaps each placeholder for its original name,
        optionally re-attaching the ``data-dita-seg-id`` attribute when present
        in the placeholder tag.

        :param tree: Minimal XML tree to update.
        :param mappings: Placeholder mapping produced earlier.
        :returns: ``None``.
        """

        for elem in tree.getroot().iter():
            tag = elem.tag
            seg_id = None
            if "_" in tag:
                placeholder, seg_id = tag.split("_", 1)
            else:
                placeholder = tag
            elem.tag = mappings.get(placeholder, placeholder)
            if seg_id:
                elem.set("data-dita-seg-id", seg_id)

    def _merge_simple(self, simple_root: etree._Element, skeleton_root: etree._Element) -> None:
        """Merge translated minimal XML with the original skeleton.

        The algorithm walks both trees simultaneously, aligning nodes by
        ``data-dita-seg-id`` when present or by tag order otherwise.  Attributes
        from the skeleton are preserved if missing in the translated fragment to
        avoid losing metadata.  The method mutates ``skeleton_root`` in place.

        :param simple_root: Root of the translated minimal XML.
        :param skeleton_root: Root of the skeleton XML to update.
        :returns: ``None``.
        """

        def copy_attrs(src: etree._Element, dst: etree._Element) -> None:
            for k, v in dst.attrib.items():
                if k not in src.attrib:
                    src.set(k, v)

        def merge(trans_elem: etree._Element, skel_elem: etree._Element) -> None:
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

        for seg_elem in simple_root.xpath("//*[@data-dita-seg-id]"):
            seg_id = seg_elem.get("data-dita-seg-id")
            match = skeleton_root.xpath(f"//*[@data-dita-seg-id='{seg_id}']")
            if match:
                merge(seg_elem, match[0])

    def _resolve(self, path: str, base: str | None) -> str:
        """Normalize file paths for convenience.

        Many public methods allow callers to pass just a basename.  This helper
        joins such names with a provided base directory so tests can use
        temporary folders without computing full paths themselves.

        :param path: User supplied path, possibly just a filename.
        :param base: Directory to prepend when ``path`` has no directory part.
        :returns: An absolute or relative path ready for I/O operations.
        """

        if os.path.isabs(path) or os.path.dirname(path):
            return path
        if base:
            return os.path.join(base, path)
        return path

    def _detect_encoding(self, xml_path: str) -> str:
        """Detect the declared XML encoding.

        Reading only the header keeps the operation fast while covering typical
        declarations.  If no encoding is specified ``utf-8`` is assumed, which
        matches the DITA default.

        :param xml_path: Path to the XML file.
        :returns: The encoding string.
        """

        with open(xml_path, "rb") as f:
            header = f.read(200).decode("ascii", errors="ignore")
        match = re.search(r"encoding=[\"']([^\"']+)[\"']", header)
        return match.group(1) if match else "utf-8"

    def parse(
        self,
        xml_path: str,
        skeleton_path: str | None = None,
        segments_path: str | None = None,
    ) -> Tuple[List[dict], str]:
        """Convert a source XML file into translation-ready artifacts.

        The parser assigns stable identifiers to each translatable container and
        writes two files: a skeleton XML preserving structure and a JSON list of
        segments.  A minimal XML with placeholders is also produced for simple
        editing scenarios.  The return value allows callers to further process
        the segments before integration.

        :param xml_path: Path to the source XML topic.
        :param skeleton_path: Optional destination for the skeleton XML.
        :param segments_path: Optional path for the segments JSON.
        :returns: ``(segments, skeleton_path)`` where ``segments`` is a list of
            dictionaries.
        """

        xml_path = self._resolve(xml_path, self.source_dir)
        self._init_log(xml_path)
        self.logger.info("Start parse: %s", xml_path)
        encoding = self._detect_encoding(xml_path)
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(xml_path, parser)
        root = tree.getroot()
        base = os.path.splitext(os.path.basename(xml_path))[0]
        base_dir = self.intermediate_dir or os.path.dirname(skeleton_path or xml_path) or "."
        dnt_map_path = os.path.join(base_dir, f"{base}.dnt.json")
        self._extract_dnt(root, dnt_map_path)
        ids: List[Tuple[etree._Element, str]] = []
        count = 0
        # Only iterate over element nodes to avoid comments and processing
        # instructions which do not support attributes.
        for elem in root.iter("*"):
            if utils.is_container(elem):
                if "data-dita-seg-id" not in elem.attrib:
                    seg_id = utils.generate_id()
                    elem.set("data-dita-seg-id", seg_id)
                else:
                    seg_id = elem.get("data-dita-seg-id")
                ids.append((elem, seg_id))
                count += 1
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
        """Produce a translated XML file from a segments JSON.

        The method resolves any relative paths, loads the skeleton created
        during :meth:`parse`, applies the provided translations and writes the
        final XML.  It logs each step so issues can be traced after the fact.

        :param translation_json_path: JSON file with translated segments.
        :param skeleton_path: Optional path to the skeleton XML to use.
        :param output_path: Optional destination for the resulting XML.
        :returns: Path to the written translated XML file.
        """

        translation_json_path = self._resolve(translation_json_path, self.intermediate_dir)
        self._ensure_log(translation_json_path)
        self.logger.info("Start integrate: %s", translation_json_path)
        with open(translation_json_path, "r", encoding="utf-8") as f:
            translations = json.load(f)
        if isinstance(translations, dict):
            translations = [translations]
        name = os.path.splitext(os.path.basename(translation_json_path))[0]
        suffix = f".{self.target_lang}_translated"
        json_base = name[:-len(suffix)] if name.endswith(suffix) else name.split(".")[0]
        if skeleton_path is None:
            skel_base = self.intermediate_dir or os.path.dirname(translation_json_path)
            skeleton_path = os.path.join(skel_base, f"{json_base}.skeleton.xml")
        else:
            skeleton_path = self._resolve(skeleton_path, self.intermediate_dir)
        base = os.path.splitext(os.path.basename(skeleton_path))[0]
        if base.endswith('.skeleton'):
            base = base[:-9]
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(skeleton_path, parser)
        root = tree.getroot()
        self._apply_translations(root, translations)
        self._remove_seg_ids(root)
        dnt_dir = os.path.dirname(skeleton_path)
        dnt_map_path = os.path.join(dnt_dir, f"{base}.dnt.json")
        if not os.path.exists(dnt_map_path):
            cand = [f for f in os.listdir(dnt_dir) if f.endswith('.dnt.json')]
            if len(cand) == 1:
                dnt_map_path = os.path.join(dnt_dir, cand[0])
        self._restore_dnt(root, dnt_map_path)
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
        self.logger.info("Skeleton used: %s", skeleton_path)
        self.logger.info("Wrote integrated file: %s", target_path)
        self.logger.info("End integrate")
        return target_path

    def validate(self, src_xml: str, tgt_xml: str) -> ValidationReport:
        """Run :class:`DitaValidator` on a pair of files.

        Convenience wrapper that resolves relative paths using the object's
        directories before delegating to :class:`DitaValidator`.

        :param src_xml: Source XML document path.
        :param tgt_xml: Translated XML document path.
        :returns: Validation results.
        """

        src_xml = self._resolve(src_xml, self.source_dir)
        tgt_xml = self._resolve(tgt_xml, self.target_dir)
        self._ensure_log(src_xml)
        skel_dir = self.intermediate_dir or os.path.dirname(tgt_xml)
        return self.validator.validate(src_xml, tgt_xml, skel_dir)

    def generate_dummy_translation(self, segments_json_path: str, output_path: str) -> str:
        """Generate a fake translation file for unit tests.

        Each source segment is prefixed with ``[<lang>_<n>]`` to make it obvious
        that the data is synthetic.  This allows the rest of the workflow to be
        exercised without contacting a real translation service.

        :param segments_json_path: Path to the original segments JSON.
        :param output_path: Location to write the dummy translation file.
        :returns: Path to the created file.
        """

        segments_json_path = self._resolve(segments_json_path, self.intermediate_dir)
        output_path = self._resolve(output_path, self.intermediate_dir)
        self._ensure_log(segments_json_path)
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
        self.logger.info("Dummy translation written: %s", output_path)
        return output_path

    def integrate_from_simple_xml(self, simple_xml_path: str) -> Tuple[str, ValidationReport]:
        """Integrate a translated minimal XML back into full form.

        The minimal XML uses placeholder tags and embeds the segment ID within
        the tag name.  This method reverses that transformation by using the
        stored mapping and skeleton.  It is useful when translators edit the
        minimal form directly rather than sending JSON segments back.

        :param simple_xml_path: Path to the translated minimal XML file.
        :returns: Tuple of the output XML path and the validation report.
        """
        simple_xml_path = self._resolve(simple_xml_path, self.intermediate_dir)
        self._ensure_log(simple_xml_path)
        self.logger.info("Start integrate from simple XML: %s", simple_xml_path)

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

        mappings = self._load_mappings(mapping_path)
        self._replace_placeholders(simple_tree, mappings)

        skeleton_tree = etree.parse(skeleton_path, parser)
        skeleton_root = skeleton_tree.getroot()

        self._merge_simple(simple_tree.getroot(), skeleton_root)

        self._remove_seg_ids(skeleton_root)
        dnt_map_path = os.path.join(base_dir, f"{base}.dnt.json")
        if not os.path.exists(dnt_map_path):
            cand = [f for f in os.listdir(base_dir) if f.endswith('.dnt.json')]
            if len(cand) == 1:
                dnt_map_path = os.path.join(base_dir, cand[0])
        self._restore_dnt(skeleton_root, dnt_map_path)

        out_base = self.target_dir or base_dir
        target_path = os.path.join(out_base, f"{base}.xml")
        skeleton_tree.write(
            target_path,
            encoding="utf-8",
            xml_declaration=True,
            doctype=skeleton_tree.docinfo.doctype,
            pretty_print=True,
        )
        report = self.validate(source_xml_path, target_path)
        self.logger.info("End integrate from simple XML")
        return target_path, report
