# DITA XML LLM Transformer

This project provides utilities for preparing DITA or generic XML documents for
translation with large language models. The workflow extracts translatable
segments, generates a simplified XML containing stable placeholders and merges
the translated output back into the original structure. Validation helpers ensure
that no markup is lost in the round trip.

## Installation

Clone the repository and install the dependencies. A standard ``requirements``
file is provided and the project can be installed as a package if desired:

```bash
pip install -r requirements.txt
pip install -e .  # optional, allows ``import dita_xml_parser`` anywhere
```

Running the tests verifies that everything works as expected:

```bash
pytest
```

## Package layout

```
dita_xml_parser/
├── transformer.py  # Dita2LLM main workflow class
├── validator.py    # XML structure validation utilities
├── utils.py        # helper functions for XML manipulation
├── minimal.py      # create minimal placeholder XML files
└── __init__.py     # exposes package classes for import
```

Example DITA files are provided in `sample_data/` and unit tests live in `tests/`.

## Features

- Extracts translatable text segments while preserving XML markup
- Generates minimal placeholder XML for translation tools
- Merges translated content back into the original file
- Validates the output to ensure structural fidelity
- Supports configuration via a small ``TOML`` file

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

# Merge translations back into the skeleton and validate the result
target_path = tr.integrate("sample_topic.translated.json")
report = tr.validate("sample_topic.xml", target_path)
print("validation", "passed" if report.passed else "failed")
```

## Development

The repository ships with unit tests and a ``pylint`` configuration. Run the
following commands to ensure code quality:

```bash
pytest       # run unit tests
pylint dita_xml_parser
```

For simple workflows you can translate the generated `*.minimal.xml` and call `integrate_from_simple_xml` to reconstruct the original document.

### Configuration

Runtime behaviour can be tweaked using a small ``TOML`` file. Set the
``DITA_PARSER_CONFIG`` environment variable to point at your configuration file
or place ``config.toml`` next to ``config.py``. The following keys are
supported:

- ``INLINE_TAGS``: list of inline element names
- ``ID_LENGTH``: length of generated segmentation IDs
- ``LOG_LEVEL``: default logger level

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
