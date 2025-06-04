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

segments, skeleton = tr.parse("sample_data/sample_topic.xml")

# Normally the segments would be sent for translation
tr.generate_dummy_translation(
    "intermediate/sample_topic.en-US_segments.json",
    "intermediate/sample_topic.translated.json",
)

# Merge translations back into the skeleton
tr.integrate("intermediate/sample_topic.translated.json")

# Validate the result
report = tr.validate("sample_data/sample_topic.xml", tr._last_target_path)
print("validation", "passed" if report.passed else "failed")
```

For simple workflows you can translate the generated `*.minimal.xml` and call `integrate_from_simple_xml` to reconstruct the original document.
