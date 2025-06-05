import os
import sys
import logging
import io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lxml import etree

from dita_xml_parser import Dita2LLM
from dita_xml_parser import minimal, utils


def make_transformer(tmp_path):
    intermediate = tmp_path / 'intermediate'
    target = tmp_path / 'translated'
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM('sample_data', str(intermediate), str(target))


def test_get_inner_xml_mixed_content():
    elem = etree.fromstring('<p>pre <b>bold</b> mid <i>ital</i> tail</p>')
    inner = utils.get_inner_xml(elem)
    assert inner == 'pre <b>bold</b> mid <i>ital</i> tail'


def test_set_inner_xml_invalid_fragment():
    elem = etree.Element('p')
    utils.set_inner_xml(elem, 'foo & bar')
    assert elem.text == 'foo & bar'


def test_write_minimal_strips_comments_and_pi(tmp_path):
    xml = '<?xml version="1.0"?><topic><!--c--><?proc a?>\n<p>t</p></topic>'
    tree = etree.fromstring(xml)
    et = etree.ElementTree(tree)
    logger = logging.getLogger("test")
    minimal.write_minimal(et, 'x', str(tmp_path), 'utf-8', logger)
    out = (tmp_path / 'x.minimal.xml').read_text(encoding='utf-8')
    assert '<!--' not in out
    assert '<?proc' not in out


def test_write_minimal_handles_top_level_comments(tmp_path):
    xml = '<!--top--><?pi?><topic>t</topic>'
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(io.StringIO(xml), parser)
    logger = logging.getLogger("test")
    # Should not raise when removing comments without a parent
    minimal.write_minimal(tree, 'y', str(tmp_path), 'utf-8', logger)
    out = (tmp_path / 'y.minimal.xml').read_text(encoding='utf-8')
    assert '<!--' not in out
    assert '<?pi' not in out


def test_is_container_with_tail_text():
    elem = etree.fromstring('<p><b>b</b> tail</p>')
    assert utils.is_container(elem)


def test_remove_seg_ids_after_integration(tmp_path):
    tr = make_transformer(tmp_path)
    tr.parse('sample_topic.xml')
    seg = tmp_path / 'intermediate' / 'sample_topic.en-US_segments.json'
    out = tmp_path / 'intermediate' / 'sample_topic.translated.json'
    tr.generate_dummy_translation(str(seg), str(out))
    target = tr.integrate(str(out))
    tree = etree.parse(target)
    assert not tree.xpath('//*[@data-dita-seg-id]')


def test_detect_encoding_non_utf8(tmp_path):
    path = tmp_path / 'enc.xml'
    text = '<?xml version="1.0" encoding="ISO-8859-1"?><topic>ä</topic>'
    path.write_bytes(text.encode('iso-8859-1'))
    tr = Dita2LLM(None, None, None)
    assert tr._detect_encoding(str(path)).lower() == 'iso-8859-1'


def test_apply_translations_styles():
    root = etree.fromstring('<topic><p data-dita-seg-id="1">t</p></topic>')
    tr = Dita2LLM(None, None, None)
    tr._apply_translations(root, [{'1': 'A'}, {'id': '2', 'de-DE': 'B'}])
    assert root.xpath('//p')[0].text == 'A'
