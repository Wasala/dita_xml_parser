import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
from lxml import etree
from dita_xml_parser import Dita2LLM
import config

COMPLEX_TOPIC = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'complex_topic.xml')
SIMPLE_CONCEPT = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'simple_concept.xml')
SAMPLE_MAP = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'sample_map.ditamap')


def make_transformer(tmp_path):
    intermediate = tmp_path / 'intermediate'
    target = tmp_path / 'translated'
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM('sample_data', str(intermediate), str(target))


def test_nested_paragraph_inner_xml(tmp_path):
    tr = make_transformer(tmp_path)
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(COMPLEX_TOPIC, parser)
    p_elem = tree.xpath('//p')[0]
    inner = tr._get_inner_xml(p_elem)
    assert 'Beginning text' in inner
    assert '<ul>' in inner
    assert 'some mid text' in inner
    tr._set_inner_xml(p_elem, inner)
    assert tr._get_inner_xml(p_elem) == inner


def test_complex_topic_parse_and_validate(tmp_path):
    tr = make_transformer(tmp_path)
    segments, skeleton = tr.parse(COMPLEX_TOPIC)
    # ensure multiple segments detected
    assert len(segments) >= 5
    seg_path = tmp_path / 'intermediate' / 'complex_topic.en-US_segments.json'
    dummy_path = tmp_path / 'intermediate' / 'complex_topic.translated.json'
    tr.generate_dummy_translation(str(seg_path), str(dummy_path))
    target_path = tr.integrate(str(dummy_path))
    report = tr.validate(COMPLEX_TOPIC, target_path)
    assert report.passed


def test_concept_parse_and_validate(tmp_path):
    tr = make_transformer(tmp_path)
    segments, skeleton = tr.parse(SIMPLE_CONCEPT)
    seg_path = tmp_path / 'intermediate' / 'simple_concept.en-US_segments.json'
    dummy_path = tmp_path / 'intermediate' / 'simple_concept.translated.json'
    tr.generate_dummy_translation(str(seg_path), str(dummy_path))
    target_path = tr.integrate(str(dummy_path))
    report = tr.validate(SIMPLE_CONCEPT, target_path)
    assert report.passed


def test_map_parse(tmp_path):
    tr = make_transformer(tmp_path)
    segments, skeleton = tr.parse(SAMPLE_MAP)
    seg_path = tmp_path / 'intermediate' / 'sample_map.en-US_segments.json'
    assert os.path.exists(str(seg_path))
    assert os.path.exists(str(skeleton))
