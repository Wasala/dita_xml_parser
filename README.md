# DITA XML LLM Transformer

This package provides a workflow for extracting translatable segments from DITA/XML files, generating minimal token versions for LLM translation, and reintegrating translated text. Each XML tag is replaced by a stable placeholder so that the same element type always maps to the same token.

## Setup

```
pip install -r requirements.txt  # installs lxml
```

## Usage

```
from dita_xml_parser import Dita2LLM

transformer = Dita2LLM(
    source_dir='sample_data',
    intermediate_dir='intermediate',
    target_dir='translated',
    source_lang='en-US',
    target_lang='de-DE',
    log_dir='logs'
)

segments, skeleton = transformer.parse('sample_data/sample_topic.xml')
# create dummy translation
transformer.generate_dummy_translation(os.path.join('intermediate','sample_topic.en-US_segments.json'),
                                       os.path.join('intermediate','sample_topic.translated.json'))
transformer.integrate(os.path.join('intermediate','sample_topic.translated.json'))
report = transformer.validate('sample_data/sample_topic.xml', transformer._last_target_path)
print('Validation', 'passed' if report.passed else 'failed')
```

Outputs appear in `intermediate/`, `translated/`, and `logs/`.
