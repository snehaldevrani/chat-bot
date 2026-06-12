import re
from typing import Tuple
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|initial|your)\s+(instructions?|prompts?|rules?|directives?|guidelines?)",
    r"forget\s+(everything|all|previous|prior|your\s+instructions?)",
    r"disregard\s+(all\s+)?(previous|prior|initial)?\s*(instructions?|prompts?|rules?)",
    r"you\s+are\s+now\s+(?!a\s+parking)",
    r"act\s+as\s+(?!a\s+parking)",
    r"\bjailbreak\b",
    r"bypass\s+(the\s+)?(rules?|restrictions?|guidelines?|filters?|safety)",
    r"override\s+(your|the)\s+(instructions?|rules?|programming|guidelines?)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"roleplay\s+as",
    r"\bDAN\b",
    r"prompt\s+injection",
    r"system\s+prompt",
    r"reveal\s+(your|the)\s+(instructions?|prompt|system)",
]

SENSITIVE_OUTPUT_ENTITIES = [
    "CREDIT_CARD",
    "US_SSN",
    "IBAN_CODE",
    "US_BANK_NUMBER",
    "CRYPTO",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
]

_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer


def _get_anonymizer() -> AnonymizerEngine:
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


class InputFilter:
    def check(self, text: str) -> Tuple[bool, str]:
        text_lower = text.lower()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                return True, "This looks like a prompt injection attempt."
        return False, ""


class OutputFilter:
    def clean(self, text: str) -> str:
        try:
            analyzer = _get_analyzer()
            results = analyzer.analyze(
                text=text,
                entities=SENSITIVE_OUTPUT_ENTITIES,
                language="en",
            )
            if not results:
                return text
            anonymizer = _get_anonymizer()
            return anonymizer.anonymize(text=text, analyzer_results=results).text
        except Exception:
            return text


_input_filter: InputFilter | None = None
_output_filter: OutputFilter | None = None


def get_input_filter() -> InputFilter:
    global _input_filter
    if _input_filter is None:
        _input_filter = InputFilter()
    return _input_filter


def get_output_filter() -> OutputFilter:
    global _output_filter
    if _output_filter is None:
        _output_filter = OutputFilter()
    return _output_filter
