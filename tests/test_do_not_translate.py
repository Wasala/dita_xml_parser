import os
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from lxml import etree
from dita_xml_parser import Dita2LLM


def make_transformer(tmp_path):
    intermediate = tmp_path / "intermediate"
    target = tmp_path / "translated"
    intermediate.mkdir()
    target.mkdir()
    return Dita2LLM(str(tmp_path), str(intermediate), str(target))


def create_xml(tmp_path):
    xml = (
        "<?xml version='1.0'?><topic><body>"
        "<p>Press <uicontrol>OK</uicontrol> now.</p>"
        "</body></topic>"
    )
    path = tmp_path / "dnt.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_dnt_not_in_segments(tmp_path):
    tr = make_transformer(tmp_path)
    xml_path = create_xml(tmp_path)
    segments, _ = tr.parse(str(xml_path))
    assert all("<uicontrol>" not in s[tr.source_lang] for s in segments)
    skel = tmp_path / "intermediate" / "dnt.skeleton.xml"
    tree = etree.parse(str(skel))
    dnt = tree.xpath("//dnt")[0]
    assert dnt.get("element") == "uicontrol"
    assert dnt.get("content") == "OK"


def test_dnt_restored_from_json(tmp_path):
    tr = make_transformer(tmp_path)
    xml_path = create_xml(tmp_path)
    tr.parse(str(xml_path))
    seg_path = tmp_path / "intermediate" / "dnt.en-US_segments.json"
    out_path = tmp_path / "intermediate" / "dnt.translated.json"
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    skel = tmp_path / "intermediate" / "dnt.skeleton.xml"
    tree = etree.parse(str(skel))
    dnt = tree.xpath("//dnt")[0]
    dnt.set("content", "CHANGED")
    tree.write(str(skel), encoding="utf-8")
    target = tr.integrate(str(out_path))
    final = etree.parse(str(target))
    assert final.xpath("//uicontrol")[0].text == "OK"


def test_dnt_restored_from_simple_xml(tmp_path):
    tr = make_transformer(tmp_path)
    xml_path = create_xml(tmp_path)
    tr.parse(str(xml_path))
    minimal = tmp_path / "intermediate" / "dnt.minimal.xml"
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(minimal), parser)
    for el in tree.getroot().iter():
        if el.text and el.text.strip():
            el.text = "t " + el.text
    trans_path = minimal.with_name(minimal.stem + ".translated.xml")
    tree.write(str(trans_path), encoding="utf-8", pretty_print=True)
    target, report = tr.integrate_from_simple_xml(str(trans_path))
    assert report.passed
    final = etree.parse(str(target))
    assert final.xpath("//uicontrol")[0].text == "OK"


def test_dnt_restored_without_mapping_file(tmp_path):
    tr = make_transformer(tmp_path)
    xml_path = create_xml(tmp_path)
    tr.parse(str(xml_path))
    seg_path = tmp_path / "intermediate" / "dnt.en-US_segments.json"
    out_path = tmp_path / "intermediate" / "dnt.translated.json"
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    mapping = tmp_path / "intermediate" / "dnt.dnt.json"
    if mapping.exists():
        mapping.unlink()
    target = tr.integrate(str(out_path))
    final = etree.parse(str(target))
    assert final.xpath("//uicontrol")[0].text == "OK"


def test_dnt_restored_missing_id_in_mapping(tmp_path):
    tr = make_transformer(tmp_path)
    xml_path = create_xml(tmp_path)
    tr.parse(str(xml_path))
    seg_path = tmp_path / "intermediate" / "dnt.en-US_segments.json"
    out_path = tmp_path / "intermediate" / "dnt.translated.json"
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    mapping = tmp_path / "intermediate" / "dnt.dnt.json"
    with open(mapping, "r", encoding="utf-8") as f:
        data = json.load(f)
    key = next(iter(data))
    del data[key]
    with open(mapping, "w", encoding="utf-8") as f:
        json.dump(data, f)
    target = tr.integrate(str(out_path))
    final = etree.parse(str(target))
    assert final.xpath("//uicontrol")[0].text == "OK"


def test_dnt_restored_without_id(tmp_path):
    tr = make_transformer(tmp_path)
    xml_path = create_xml(tmp_path)
    tr.parse(str(xml_path))
    seg_path = tmp_path / "intermediate" / "dnt.en-US_segments.json"
    out_path = tmp_path / "intermediate" / "dnt.translated.json"
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    skeleton = tmp_path / "intermediate" / "dnt.skeleton.xml"
    tree = etree.parse(str(skeleton))
    dnt = tree.xpath("//dnt")[0]
    if "id" in dnt.attrib:
        del dnt.attrib["id"]
    tree.write(str(skeleton), encoding="utf-8")
    target = tr.integrate(str(out_path))
    final = etree.parse(str(target))
    assert final.xpath("//uicontrol")[0].text == "OK"


def test_dnt_restored_without_id_or_mapping(tmp_path):
    tr = make_transformer(tmp_path)
    xml_path = create_xml(tmp_path)
    tr.parse(str(xml_path))
    seg_path = tmp_path / "intermediate" / "dnt.en-US_segments.json"
    out_path = tmp_path / "intermediate" / "dnt.translated.json"
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    skeleton = tmp_path / "intermediate" / "dnt.skeleton.xml"
    tree = etree.parse(str(skeleton))
    dnt = tree.xpath("//dnt")[0]
    if "id" in dnt.attrib:
        del dnt.attrib["id"]
    tree.write(str(skeleton), encoding="utf-8")
    mapping = tmp_path / "intermediate" / "dnt.dnt.json"
    if mapping.exists():
        mapping.unlink()
    target = tr.integrate(str(out_path))
    final = etree.parse(str(target))
    assert final.xpath("//uicontrol")[0].text == "OK"


def test_nested_dnt_integration(tmp_path):
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?><topic><body><p>Die "
        "<ph><uicontrol>Boot Manager</uicontrol></ph> jetzt.</p></body></topic>"
    )
    xml_path = tmp_path / "nested.xml"
    xml_path.write_text(xml, encoding="utf-8")
    tr = make_transformer(tmp_path)
    tr.parse(str(xml_path))
    seg_path = tmp_path / "intermediate" / "nested.en-US_segments.json"
    out_path = tmp_path / "intermediate" / "nested.translated.json"
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    target = tr.integrate(str(out_path))
    tree = etree.parse(str(target))
    assert not tree.xpath("//dnt")
    assert tree.xpath("//ph/uicontrol")[0].text == "Boot Manager"


def test_integration_preserves_encoding(tmp_path):
    xml = (
        "<?xml version='1.0' encoding='ISO-8859-1'?>"
        "<topic><body><p>Die <uicontrol>Boot</uicontrol></p></body></topic>"
    )
    xml_path = tmp_path / "enc.xml"
    xml_path.write_bytes(xml.encode("iso-8859-1"))
    tr = make_transformer(tmp_path)
    tr.parse(str(xml_path))
    seg_path = tmp_path / "intermediate" / "enc.en-US_segments.json"
    out_path = tmp_path / "intermediate" / "enc.translated.json"
    tr.generate_dummy_translation(str(seg_path), str(out_path))
    target = tr.integrate(str(out_path))
    with open(target, "rb") as f:
        header = f.read(80)
    assert b"ISO-8859-1" in header

