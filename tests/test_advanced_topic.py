import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lxml import etree
from dita_xml_parser import Dita2LLM

ADV_XML = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'advanced_topic.xml')


def make_transformer(tmp_path):
    intermediate = tmp_path / 'intermediate'
    target = tmp_path / 'translated'
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM('sample_data', str(intermediate), str(target))


def build_translated_simple(minimal_path):
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(minimal_path), parser)
    for elem in tree.getroot().iter():
        if elem.text and elem.text.strip():
            elem.text = 'translated ' + elem.text
    out_path = minimal_path.parent / (minimal_path.stem + '.translated.xml')
    tree.write(str(out_path), encoding='utf-8', pretty_print=True)
    return out_path


def test_advanced_dummy_translation_workflow(tmp_path):
    tr = make_transformer(tmp_path)
    segments, skeleton = tr.parse(ADV_XML)
    assert len(segments) > 10
    seg_path = tmp_path / 'intermediate' / 'advanced_topic.en-US_segments.json'
    dummy_path = tmp_path / 'intermediate' / 'advanced_topic.translated.json'
    tr.generate_dummy_translation(str(seg_path), str(dummy_path))
    target_path = tr.integrate(str(dummy_path))
    report = tr.validate(ADV_XML, target_path)
    assert report.passed


def test_advanced_simple_xml_integration(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(ADV_XML)
    minimal = tmp_path / 'intermediate' / 'advanced_topic.minimal.xml'
    translated = build_translated_simple(minimal)
    target_path, report = tr.integrate_from_simple_xml(str(translated))
    assert report.passed
    tree = etree.parse(str(target_path))
    assert tree.xpath('//title')[0].text.startswith('translated')

