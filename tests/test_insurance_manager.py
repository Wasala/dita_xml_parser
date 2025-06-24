import os
import sys
from lxml import etree
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dita_xml_parser import Dita2LLM

INSURANCE_XML = os.path.join(os.path.dirname(__file__), '..', 'sample_data', 'insurance_manager.xml')


def make_transformer(tmp_path):
    intermediate = tmp_path / 'intermediate'
    target = tmp_path / 'translated'
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM('sample_data', str(intermediate), str(target))


def test_insurance_uicontrol_preserved(tmp_path):
    tr = make_transformer(tmp_path)
    segments, _ = tr.parse(INSURANCE_XML)
    assert len(segments) > 0
    seg_path = tmp_path / 'intermediate' / 'insurance_manager.en-US_segments.json'
    out_path = tmp_path / 'intermediate' / 'insurance_manager.translated.json'
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    target_path = tr.integrate(str(out_path))
    tree = etree.parse(str(target_path))
    texts = [el.text for el in tree.xpath('//uicontrol')]
    assert all(t == 'Insurance Control' for t in texts)
