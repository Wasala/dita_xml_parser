import os
import json
import logging
import datetime
import copy
from typing import List, Tuple
from lxml import etree
from secrets import token_hex

import config

class ValidationReport:
    def __init__(self, passed: bool, details: List[str]):
        self.passed = passed
        self.details = details

class Dita2LLM:
    def __init__(self, source_dir: str, intermediate_dir: str, target_dir: str,
                 source_lang: str = "en-US", target_lang: str = "de-DE",
                 log_dir: str = "logs"):
        self.source_dir = source_dir
        self.intermediate_dir = intermediate_dir
        self.target_dir = target_dir
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.log_dir = log_dir
        os.makedirs(self.intermediate_dir, exist_ok=True)
        os.makedirs(self.target_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        self.logger = logging.getLogger("Dita2LLM")
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL))
        self._last_target_path = None

    # Utility functions
    def _init_log(self, xml_path: str):
        for h in list(self.logger.handlers):
            self.logger.removeHandler(h)
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        base = os.path.splitext(os.path.basename(xml_path))[0]
        log_path = os.path.join(self.log_dir, f"{base}_{ts}.log")
        fh = logging.FileHandler(log_path)
        formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        return log_path

    def _generate_id(self) -> str:
        return token_hex(config.ID_LENGTH // 2)

    def _has_inline_child(self, elem: etree._Element) -> bool:
        for child in elem:
            if child.tag in config.INLINE_TAGS:
                return True
        return False

    def _is_container(self, elem: etree._Element) -> bool:
        if elem.tag in config.INLINE_TAGS:
            return False
        if (elem.text and elem.text.strip()):
            return True
        for child in elem:
            if (child.tail and child.tail.strip()) or child.tag in config.INLINE_TAGS:
                return True
        return False

    def _get_inner_xml(self, elem: etree._Element) -> str:
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(etree.tostring(child, encoding=str))
        return ''.join(parts)

    def parse(self, xml_path: str) -> Tuple[List[dict], str]:
        log_path = self._init_log(xml_path)
        self.logger.info(f"Start parse: {xml_path}")
        with open(xml_path, 'rb') as f:
            header = f.read(200).decode('ascii', errors='ignore')
        encoding = 'utf-8'
        if 'encoding' in header:
            import re
            m = re.search(r'encoding=["\']([^"\']+)["\']', header)
            if m:
                encoding = m.group(1)
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(xml_path, parser)
        root = tree.getroot()
        ids = []
        count = 0
        for elem in root.iter():
            if self._is_container(elem):
                if 'data-dita-seg-id' not in elem.attrib:
                    seg_id = self._generate_id()
                    elem.set('data-dita-seg-id', seg_id)
                else:
                    seg_id = elem.get('data-dita-seg-id')
                ids.append((elem, seg_id))
                count += 1
        base = os.path.splitext(os.path.basename(xml_path))[0]
        skeleton_path = os.path.join(self.intermediate_dir, f"{base}.skeleton.xml")
        tree.write(skeleton_path, encoding=encoding, xml_declaration=True,
                   doctype=tree.docinfo.doctype)
        segments = []
        for elem, seg_id in ids:
            segments.append({"id": seg_id, self.source_lang: self._get_inner_xml(elem)})
        segments_path = os.path.join(self.intermediate_dir,
                                     f"{base}.{self.source_lang}_segments.json")
        with open(segments_path, 'w', encoding='utf-8') as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        self._write_minimal(tree, base, encoding)
        self.logger.info(f"Containers found: {count}")
        self.logger.info(f"JSON segments written: {len(segments)}")
        self.logger.info(f"Skeleton path: {skeleton_path}")
        self.logger.info("End parse")
        return segments, skeleton_path

    def _write_minimal(self, tree: etree._ElementTree, base: str, encoding: str):
        minimal = copy.deepcopy(tree)
        # remove comments and processing instructions
        for el in minimal.xpath('//comment()'):
            el.getparent().remove(el)
        for el in minimal.xpath('//processing-instruction()'):
            el.getparent().remove(el)
        placeholder_map = {}
        counter = 1
        for elem in minimal.iter():
            placeholder = f"t{counter}"
            placeholder_map[placeholder] = elem.tag
            new_tag = placeholder
            seg_id = elem.get('data-dita-seg-id')
            # strip all attributes; seg id will be encoded in the tag name
            for attr in list(elem.attrib):
                del elem.attrib[attr]
            if seg_id:
                new_tag = f"{placeholder}_{seg_id}"
            elem.tag = new_tag
            counter += 1
        minimal_path = os.path.join(self.intermediate_dir, f"{base}.minimal.xml")
        minimal_tree = etree.ElementTree(minimal.getroot())
        minimal_tree.write(minimal_path, encoding=encoding, xml_declaration=False, pretty_print=True)
        mapping_path = os.path.join(self.intermediate_dir, f"{base}.tag_mappings.txt")
        with open(mapping_path, 'w', encoding='utf-8') as f:
            for placeholder, original in placeholder_map.items():
                f.write(f"{placeholder} -> {original}\n")
        self.logger.info(f"Minimal XML tags generated: {counter-1}")
        self.logger.info(f"Minimal XML path: {minimal_path}")
        self.logger.info(f"Mapping path: {mapping_path}")

    def integrate(self, translation_json_path: str) -> str:
        self.logger.info(f"Start integrate: {translation_json_path}")
        with open(translation_json_path, 'r', encoding='utf-8') as f:
            translations = json.load(f)
        if isinstance(translations, dict):
            translations = [translations]
        # Determine base name
        name = os.path.splitext(os.path.basename(translation_json_path))[0]
        if name.endswith(f".{self.target_lang}_translated"):
            base = name[:-(len(self.target_lang)+12)]
        else:
            base = name.split('.')[0]
        skeleton_path = os.path.join(self.intermediate_dir, f"{base}.skeleton.xml")
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(skeleton_path, parser)
        root = tree.getroot()
        for idx, entry in enumerate(translations, start=1):
            if 'id' in entry:
                seg_id = entry['id']
                value = entry.get(self.target_lang) or next((v for k,v in entry.items() if k!= 'id'), '')
            else:
                seg_id, value = next(iter(entry.items()))
            elems = root.xpath(f"//*[@data-dita-seg-id='{seg_id}']")
            if not elems:
                self.logger.error(f"ID {seg_id} not found in skeleton")
                continue
            elem = elems[0]
            self._set_inner_xml(elem, value)
        # remove helper attributes before saving
        for el in root.iter():
            if 'data-dita-seg-id' in el.attrib:
                del el.attrib['data-dita-seg-id']
        target_path = os.path.join(self.target_dir, f"{base}.xml")
        tree.write(target_path, encoding='utf-8', xml_declaration=True, doctype=tree.docinfo.doctype, pretty_print=True)
        self._last_target_path = target_path
        self.logger.info(f"Wrote integrated file: {target_path}")
        self.logger.info("End integrate")
        return target_path

    def _set_inner_xml(self, elem: etree._Element, xml_string: str):
        # clear existing content
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

    def validate(self, src_xml: str, tgt_xml: str) -> ValidationReport:
        self.logger.info(f"Start validate: {src_xml} vs {tgt_xml}")
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
                    walk(c1, c2, path+"/"+e1.tag)
            elif isinstance(e1, etree._Comment) and isinstance(e2, etree._Comment):
                if e1.text != e2.text:
                    errors.append(f"comment mismatch at {path}")
            elif isinstance(e1, etree._ProcessingInstruction) and isinstance(e2, etree._ProcessingInstruction):
                if e1.target != e2.target or e1.text != e2.text:
                    errors.append(f"pi mismatch at {path}")
        walk(src_tree.getroot(), tgt_tree.getroot())
        passed = not errors
        for err in errors:
            self.logger.error(err)
        self.logger.info("End validate")
        return ValidationReport(passed, errors)

    def generate_dummy_translation(self, segments_json_path: str, output_path: str) -> str:
        with open(segments_json_path, 'r', encoding='utf-8') as f:
            segments = json.load(f)
        translations = []
        for idx, seg in enumerate(segments, start=1):
            prefix = f"[{self.target_lang}_{idx}] "
            translations.append({"id": seg['id'], self.target_lang: prefix + seg[self.source_lang]})
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(translations, f, indent=2, ensure_ascii=False)
        self.logger.info(f"Dummy translation written: {output_path}")
        return output_path

