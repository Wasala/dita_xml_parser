import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from lxml import etree
from dita_xml_parser import Dita2LLM

COMPLEX_XML_CONTENT = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="full">
  <title>Full <keyword>Keyword</keyword> Title</title>
  <shortdesc>Short <ph>desc</ph>.</shortdesc>
  <author>John Doe</author>
  <body>
    <div>
      <section id="s1">
        <title>Section 1</title>
        <p>Paragraph with <b>bold</b>, <i>italic</i>, <uicontrol>OK</uicontrol>, <codeph>code</codeph>, and <term>term</term>.</p>
        <note>Note <ph>ph content</ph>.</note>
        <example><desc>Example description</desc></example>
        <fig>
          <title>Fig Title</title>
          <figgroup><fig><title>Inner Fig</title></fig></figgroup>
        </fig>
        <ol><li>Item1 <sub>sub</sub></li><li>Item2</li></ol>
        <ul><li>U1</li><li>U2 <b><ph>placeholder</ph></b></li></ul>
        <dl><dlentry><dt>Term</dt><dd>Definition</dd></dlentry></dl>
        <table>
          <title>Table title</title>
          <tgroup cols="1">
            <tbody>
              <row><entry>Cell</entry></row>
            </tbody>
          </tgroup>
        </table>
      </section>
      <taskbody>
        <steps>
          <step>
            <cmd>Run</cmd>
            <stepresult>Done</stepresult>
          </step>
          <step>
            <info>Info</info>
            <result>Res</result>
            <substeps>
              <substep><cmd>Sub</cmd></substep>
            </substeps>
          </step>
        </steps>
      </taskbody>
    </div>
  </body>
</topic>'''

def make_transformer(tmp_path):
    intermediate = tmp_path / 'intermediate'
    target = tmp_path / 'translated'
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM(str(tmp_path), str(intermediate), str(target))


def build_translated_simple(minimal_path):
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(minimal_path), parser)
    for elem in tree.getroot().iter():
        if elem.text and elem.text.strip():
            elem.text = 'T ' + elem.text
    out_path = minimal_path.parent / (minimal_path.stem + '.translated.xml')
    tree.write(str(out_path), encoding='utf-8', pretty_print=True)
    return out_path


def test_complex_full_workflow(tmp_path):
    xml_path = tmp_path / 'complex.xml'
    xml_path.write_text(COMPLEX_XML_CONTENT, encoding='utf-8')
    tr = make_transformer(tmp_path)
    segments, skeleton = tr.parse(str(xml_path))
    assert len(segments) > 5
    skel_tree = etree.parse(str(skeleton))
    assert skel_tree.xpath('//dnt[@element="uicontrol"]')
    seg_json = tmp_path / 'intermediate' / 'complex.en-US_segments.json'
    dummy_json = tmp_path / 'intermediate' / 'complex.translated.json'
    tr.generate_dummy_translation(str(seg_json), str(dummy_json))
    target = tr.integrate(str(dummy_json))
    report = tr.validate(str(xml_path), target)
    assert report.passed
    minimal = tmp_path / 'intermediate' / 'complex.minimal.xml'
    translated = build_translated_simple(minimal)
    target2, report2 = tr.integrate_from_simple_xml(str(translated))
    assert report2.passed
    final = etree.parse(str(target2))
    assert final.xpath('//uicontrol')[0].text == 'OK'

def test_placeholder_mapping_roundtrip(tmp_path):
    xml_path = tmp_path / 'complex.xml'
    xml_path.write_text(COMPLEX_XML_CONTENT, encoding='utf-8')
    tr = make_transformer(tmp_path)
    tr.parse(str(xml_path))
    minimal_path = tmp_path / 'intermediate' / 'complex.minimal.xml'
    mapping_path = tmp_path / 'intermediate' / 'complex.tag_mappings.txt'
    skeleton_path = tmp_path / 'intermediate' / 'complex.skeleton.xml'
    parser = etree.XMLParser(remove_blank_text=False)
    simple_tree = etree.parse(str(minimal_path), parser)
    mappings = tr._load_mappings(str(mapping_path))
    tr._replace_placeholders(simple_tree, mappings)
    skeleton_tree = etree.parse(str(skeleton_path), parser)
    tr._merge_simple(simple_tree.getroot(), skeleton_tree.getroot())
    tr._remove_seg_ids(skeleton_tree.getroot())
    out_xml = tmp_path / 'merged.xml'
    skeleton_tree.write(str(out_xml), encoding='utf-8', pretty_print=True)
    assert out_xml.exists()
    merged = etree.parse(str(out_xml))
    assert merged.xpath('//cmd')[0].text in {'Run', 'T Run'}

def test_extract_and_restore_multiple_dnt(tmp_path):
    xml = '<topic><body><p>Press <uicontrol>OK</uicontrol> or <menucascade><uicontrol>A</uicontrol><uicontrol>B</uicontrol></menucascade> <cite>note</cite> <ph>ph</ph></p></body></topic>'
    root = etree.fromstring(xml)
    mapping_path = tmp_path / 'map.json'
    tr = Dita2LLM(None, None, None)
    tr._extract_dnt(root, str(mapping_path))
    assert len(root.xpath('//dnt')) == 4
    tr._restore_dnt(root, str(mapping_path))
    assert not root.xpath('//dnt')
    assert root.xpath('//uicontrol')[0].text == 'OK'

def test_resolve_and_manual_apply(tmp_path):
    xml = '<topic><title>A</title><body><p>Text</p></body></topic>'
    xml_path = tmp_path / 'r.xml'
    xml_path.write_text(xml, encoding='utf-8')
    tr = Dita2LLM(str(tmp_path), str(tmp_path / 'int'), str(tmp_path / 'out'))
    (tmp_path / 'int').mkdir(exist_ok=True)
    (tmp_path / 'out').mkdir(exist_ok=True)
    segments, _ = tr.parse(xml_path.name)
    seg_path = tmp_path / 'int' / 'r.en-US_segments.json'
    with open(seg_path, 'r', encoding='utf-8') as f:
        segs = json.load(f)
    translations = [{"id": seg["id"], tr.target_lang: 'X' + seg[tr.source_lang]} for seg in segs]
    trans_path = tmp_path / 'int' / 'r.custom.json'
    with open(trans_path, 'w', encoding='utf-8') as f:
        json.dump(translations, f, ensure_ascii=False)
    skeleton = tr._resolve('r.skeleton.xml', str(tmp_path / 'int'))
    tree = etree.parse(str(skeleton))
    tr._apply_translations(tree.getroot(), translations)
    tr._remove_seg_ids(tree.getroot())
    out = tmp_path / 'out' / 'r.xml'
    tree.write(str(out), encoding='utf-8')
    assert tr._detect_encoding(str(xml_path)) == 'utf-8'
    assert not etree.parse(str(out)).xpath('//*[@data-dita-seg-id]')

def test_manual_merge_validation(tmp_path):
    xml_path = tmp_path / 'complex.xml'
    xml_path.write_text(COMPLEX_XML_CONTENT, encoding='utf-8')
    tr = make_transformer(tmp_path)
    tr.parse(str(xml_path))
    minimal = tmp_path / 'intermediate' / 'complex.minimal.xml'
    mapping = tmp_path / 'intermediate' / 'complex.tag_mappings.txt'
    skeleton_path = tmp_path / 'intermediate' / 'complex.skeleton.xml'
    parser = etree.XMLParser(remove_blank_text=False)
    simple_tree = etree.parse(str(minimal), parser)
    for e in simple_tree.getroot().iter():
        if e.text and e.text.strip():
            e.text = 'T ' + e.text
    mappings = tr._load_mappings(str(mapping))
    tr._replace_placeholders(simple_tree, mappings)
    skeleton_tree = etree.parse(str(skeleton_path), parser)
    tr._merge_simple(simple_tree.getroot(), skeleton_tree.getroot())
    tr._remove_seg_ids(skeleton_tree.getroot())
    dnt_map = tmp_path / 'intermediate' / 'complex.dnt.json'
    tr._restore_dnt(skeleton_tree.getroot(), str(dnt_map))
    tmp_xml = tmp_path / 'manual.xml'
    skeleton_tree.write(str(tmp_xml), encoding='utf-8')
    report = tr.validate(str(xml_path), str(tmp_xml))
    assert report.passed
