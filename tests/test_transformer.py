import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
from lxml import etree
from dita_xml_parser import Dita2LLM
import config

SAMPLE_XML = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'sample_topic.xml')


def make_transformer(tmp_path):
    intermediate = tmp_path / 'intermediate'
    target = tmp_path / 'translated'
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM('sample_data', str(intermediate), str(target))


def test_generate_id_length(tmp_path):
    tr = make_transformer(tmp_path)
    seg_id = tr._generate_id()
    assert len(seg_id) == config.ID_LENGTH
    int(seg_id, 16)  # should be hex


def test_is_container_and_inline(tmp_path):
    tr = make_transformer(tmp_path)
    elem = etree.fromstring('<p>This is <b>bold</b></p>')
    assert tr._is_container(elem)
    assert tr._has_inline_child(elem)
    inline = etree.fromstring('<b>bold</b>')
    assert not tr._is_container(inline)


def test_get_and_set_inner_xml(tmp_path):
    tr = make_transformer(tmp_path)
    elem = etree.fromstring('<p>A <b>test</b></p>')
    assert tr._get_inner_xml(elem) == 'A <b>test</b>'
    tr._set_inner_xml(elem, 'Hello <i>World</i>')
    assert etree.tostring(elem, encoding='unicode') == '<p>Hello <i>World</i></p>'


def test_parse_creates_segments_and_files(tmp_path):
    tr = make_transformer(tmp_path)
    segments, skeleton = tr.parse(SAMPLE_XML)
    assert len(segments) == 9
    assert os.path.exists(skeleton)
    seg_path = tmp_path / 'intermediate' / 'sample_topic.en-US_segments.json'
    assert seg_path.exists()
    minimal_path = tmp_path / 'intermediate' / 'sample_topic.minimal.xml'
    mapping_path = tmp_path / 'intermediate' / 'sample_topic.tag_mappings.txt'
    assert minimal_path.exists() and mapping_path.exists()
    with open(seg_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert all(len(entry['id']) == config.ID_LENGTH for entry in data)


def test_generate_dummy_translation_and_integrate(tmp_path):
    tr = make_transformer(tmp_path)
    segments, _ = tr.parse(SAMPLE_XML)
    seg_path = tmp_path / 'intermediate' / 'sample_topic.en-US_segments.json'
    dummy_path = tmp_path / 'intermediate' / 'sample_topic.translated.json'
    tr.generate_dummy_translation(str(seg_path), str(dummy_path))
    with open(dummy_path, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    assert entries[0]['de-DE'].startswith('[de-DE_1]')
    target_path = tr.integrate(str(dummy_path))
    assert os.path.exists(target_path)


def test_validate_passes_for_generated_files(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    seg_path = tmp_path / 'intermediate' / 'sample_topic.en-US_segments.json'
    dummy_path = tmp_path / 'intermediate' / 'sample_topic.translated.json'
    tr.generate_dummy_translation(str(seg_path), str(dummy_path))
    target_path = tr.integrate(str(dummy_path))
    report = tr.validate(SAMPLE_XML, target_path)
    assert report.passed

def test_write_minimal_creates_placeholders(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    minimal_path = tmp_path / 'intermediate' / 'sample_topic.minimal.xml'
    mapping_path = tmp_path / 'intermediate' / 'sample_topic.tag_mappings.txt'
    with open(minimal_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '<t1>' in content
    assert '_data-dita-seg-id' not in content  # tags replaced but attribute kept
    # ensure same placeholder used for all <p> elements
    mappings = {}
    with open(mapping_path, 'r', encoding='utf-8') as f:
        for line in f:
            ph, tag = line.strip().split(' -> ')
            mappings[tag] = ph
    p_placeholder = mappings.get('p')
    assert p_placeholder is not None
    assert content.count(f'<{p_placeholder}_') >= 4  # multiple <p> tags share placeholder


def test_has_inline_child_false(tmp_path):
    tr = make_transformer(tmp_path)
    elem = etree.fromstring('<p>Just text</p>')
    assert not tr._has_inline_child(elem)


def test_is_container_false_for_inline(tmp_path):
    tr = make_transformer(tmp_path)
    inline = etree.fromstring('<b>bold</b>')
    assert not tr._is_container(inline)


def test_validate_detects_mismatch(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse(SAMPLE_XML)
    seg_path = tmp_path / 'intermediate' / 'sample_topic.en-US_segments.json'
    dummy_path = tmp_path / 'intermediate' / 'sample_topic.translated.json'
    tr.generate_dummy_translation(str(seg_path), str(dummy_path))
    target_path = tr.integrate(str(dummy_path))
    # modify the file to break validation
    with open(target_path, 'r+', encoding='utf-8') as f:
        content = f.read().replace('<title>', '<title changed="1">')
        f.seek(0)
        f.write(content)
        f.truncate()
    report = tr.validate(SAMPLE_XML, target_path)
    assert not report.passed
