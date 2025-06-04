import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lxml import etree

from dita_xml_parser import Dita2LLM

SAMPLE_XML = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'sample_topic.xml')


def make_transformer(tmp_path):
    intermediate = tmp_path / 'intermediate'
    target = tmp_path / 'translated'
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM('sample_data', str(intermediate), str(target))


def build_translated_simple(minimal_path, mapping_path, reorder=True, remove_b=False, translate_cmd=False):
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(minimal_path), parser)
    root = tree.getroot()

    mappings = {}
    with open(mapping_path, 'r', encoding='utf-8') as f:
        for line in f:
            ph, tag = line.strip().split(' -> ')
            mappings[ph] = tag

    ph_ph = next(k for k, v in mappings.items() if v == 'ph')
    ph_sub = next(k for k, v in mappings.items() if v == 'sub')
    ph_p = next(k for k, v in mappings.items() if v == 'p')
    ph_b = next(k for k, v in mappings.items() if v == 'b')
    ph_cmd = next(k for k, v in mappings.items() if v == 'cmd')

    for elem in root.iter():
        if elem.text and elem.text.strip():
            elem.text = 'translated ' + elem.text

    if reorder:
        for elem in root.iter():
            if elem.tag.startswith(ph_p + '_'):
                tags = [c.tag for c in elem]
                if any(t.startswith(ph_ph) for t in tags) and any(t.startswith(ph_sub) for t in tags):
                    ph_el = next(c for c in elem if c.tag.startswith(ph_ph))
                    sub_el = next(c for c in elem if c.tag.startswith(ph_sub))
                    elem.remove(ph_el)
                    elem.remove(sub_el)
                    elem.text = 'translated Text with '
                    sub_el.tail = ' '
                    ph_el.tail = '.'
                    elem.append(sub_el)
                    elem.append(ph_el)
                    break

    if remove_b:
        b_el = root.xpath(f'//{ph_b}')[0]
        parent = b_el.getparent()
        idx = parent.index(b_el)
        if b_el.text:
            if idx == 0:
                parent.text = (parent.text or '') + b_el.text
            else:
                prev = parent[idx - 1]
                prev.tail = (prev.tail or '') + b_el.text
        if b_el.tail:
            if idx == 0:
                parent.text = (parent.text or '') + b_el.tail
            else:
                prev = parent[idx - 1]
                prev.tail = (prev.tail or '') + b_el.tail
        parent.remove(b_el)

    if translate_cmd:
        cmd_el = root.xpath(f'//*[starts-with(name(), "{ph_cmd}_")]')[0]
        if cmd_el.text:
            cmd_el.text = 'translated ' + cmd_el.text

    out_path = minimal_path.parent / (minimal_path.stem + '.translated.xml')
    tree.write(str(out_path), encoding='utf-8', pretty_print=True)
    return out_path


def test_integrate_from_simple_xml_success(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    minimal = tmp_path / 'intermediate' / 'sample_topic.minimal.xml'
    mapping = tmp_path / 'intermediate' / 'sample_topic.tag_mappings.txt'
    translated = build_translated_simple(minimal, mapping)
    target_path, report = tr.integrate_from_simple_xml(str(translated))
    assert report.passed
    tree = etree.parse(str(target_path))
    assert tree.xpath('//title')[0].text.startswith('translated')
    assert tree.xpath('//xref')[0].get('href') == 'other.dita'


def test_integrate_from_simple_xml_order_change(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    minimal = tmp_path / 'intermediate' / 'sample_topic.minimal.xml'
    mapping = tmp_path / 'intermediate' / 'sample_topic.tag_mappings.txt'
    translated = build_translated_simple(minimal, mapping)
    target_path, report = tr.integrate_from_simple_xml(str(translated))
    assert report.passed
    tree = etree.parse(str(target_path))
    p = tree.xpath('//sub')[0].getparent()
    tags = [c.tag for c in p]
    assert tags.index('ph') < tags.index('sub')


def test_integrate_from_simple_xml_attribute_preserved(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    minimal = tmp_path / 'intermediate' / 'sample_topic.minimal.xml'
    mapping = tmp_path / 'intermediate' / 'sample_topic.tag_mappings.txt'
    translated = build_translated_simple(minimal, mapping)
    target_path, report = tr.integrate_from_simple_xml(str(translated))
    assert report.passed
    tree = etree.parse(str(target_path))
    xref = tree.xpath('//xref')[0]
    assert xref.get('href') == 'other.dita'


def test_integrate_from_simple_xml_missing_inline(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    minimal = tmp_path / 'intermediate' / 'sample_topic.minimal.xml'
    mapping = tmp_path / 'intermediate' / 'sample_topic.tag_mappings.txt'
    translated = build_translated_simple(minimal, mapping, remove_b=True)
    target, report = tr.integrate_from_simple_xml(str(translated))
    assert report.passed
    tree = etree.parse(str(target))
    assert tree.xpath('//b')


def test_integrate_from_simple_xml_nested_segment(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    minimal = tmp_path / 'intermediate' / 'sample_topic.minimal.xml'
    mapping = tmp_path / 'intermediate' / 'sample_topic.tag_mappings.txt'
    translated = build_translated_simple(minimal, mapping, translate_cmd=True)
    target_path, report = tr.integrate_from_simple_xml(str(translated))
    assert report.passed
    tree = etree.parse(str(target_path))
    cmd_text = tree.xpath('//cmd')[0].text
    assert 'translated' in cmd_text
