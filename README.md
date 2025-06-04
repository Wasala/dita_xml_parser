# DITA XML LLM Transformer

Utilities for preparing DITA/XML documents for translation with large language models. The workflow extracts translatable segments, generates a minimal XML with stable placeholders, and merges translated text back into the original structure.

## Setup

Install dependencies and run the tests to verify the environment:

```bash
pip install -r requirements.txt
pytest
```

## Package layout

```
dita_xml_parser/
├── transformer.py  # Dita2LLM main workflow class
├── utils.py        # helper functions for XML manipulation
├── minimal.py      # create minimal placeholder XML files
└── __init__.py     # exposes Dita2LLM for import
```

Example DITA files are provided in `sample_data/` and unit tests live in `tests/`.

## Basic usage

```python
from dita_xml_parser import Dita2LLM

tr = Dita2LLM(
    source_dir="sample_data",
    intermediate_dir="intermediate",
    target_dir="translated",
)

segments, skeleton = tr.parse("sample_topic.xml")  # filename only

# Normally the segments would be sent for translation
tr.generate_dummy_translation(
    "sample_topic.en-US_segments.json",
    "sample_topic.translated.json",
)

# Merge translations back into the skeleton
tr.integrate("sample_topic.translated.json")

# Validate the result
report = tr.validate("sample_topic.xml", tr._last_target_path)
print("validation", "passed" if report.passed else "failed")
```

For simple workflows you can translate the generated `*.minimal.xml` and call `integrate_from_simple_xml` to reconstruct the original document.

## Working with absolute paths

When `source_dir`, `intermediate_dir`, and `target_dir` are left unset you can
provide explicit paths to all methods. Output locations can also be overridden:

```python
from dita_xml_parser import Dita2LLM

tr = Dita2LLM()  # no base directories

xml_path = "/data/topic/sample_topic.xml"
segments_path = "/tmp/sample_topic.segs.json"
skeleton_path = "/tmp/sample_topic.skel.xml"
tr.parse(xml_path, skeleton_path=skeleton_path, segments_path=segments_path)

translated_path = "/tmp/sample_topic.translated.json"
tr.generate_dummy_translation(segments_path, translated_path)

out_xml = "/tmp/sample_topic.translated.xml"
tr.integrate(translated_path, skeleton_path=skeleton_path, output_path=out_xml)

report = tr.validate(xml_path, out_xml)
print("validation", "passed" if report.passed else "failed")
```
