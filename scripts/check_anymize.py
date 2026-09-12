"""Check live providers with fictional evidence only; never read supplier files."""

import argparse
import io
import json

from nova.config import get_settings
from nova.providers import Anymize, Gemini, ProviderUnavailable


def check(settings, *, ocr=False, with_gemini=False):
    anonymizer = Anymize(settings)
    evidence = (
        "My name is Max Mustermann. Contact me at max.mustermann@example.com. "
        "The certificate expires on 31 December 2028."
    )
    bundle = {
        "fields": [
            {"field_id": "FIELD_0001", "label": "Certificate expiry date", "field_type": "Date", "rules": {}}
        ],
        "sources": [{"source_id": "email", "text": evidence}],
    }
    sanitized_text = anonymizer.text(json.dumps(bundle))
    sanitized = json.loads(sanitized_text)
    if json.loads(anonymizer.restore(sanitized_text)) != bundle:
        raise ProviderUnavailable("Anymize did not preserve and restore the fictional evidence bundle.")
    for identifier in ("Max Mustermann", "max.mustermann@example.com"):
        if identifier.lower() in sanitized_text.lower():
            raise ProviderUnavailable("Anymize did not remove a seeded fictional identity.")
    print("Anymize text anonymization, JSON preservation, and restoration passed.", flush=True)

    if ocr:
        from reportlab.pdfgen import canvas

        stream = io.BytesIO()
        document = canvas.Canvas(stream)
        document.drawString(72, 720, "My name is Max Mustermann.")
        document.drawString(72, 700, "The certificate expires on 31 December 2028.")
        document.save()
        sanitized_document = anonymizer.document(stream.getvalue())
        restored_document = anonymizer.restore(sanitized_document)
        if "Max Mustermann" in sanitized_document or "Max Mustermann" not in restored_document:
            raise ProviderUnavailable("Anymize PDF anonymization or restoration failed the fictional check.")
        if "2028" not in sanitized_document:
            raise ProviderUnavailable("Anymize PDF processing did not preserve the fictional expiry year.")
        print("Anymize PDF processing and restoration passed.", flush=True)

    if with_gemini:
        result = Gemini(settings).evaluate(sanitized["fields"], sanitized["sources"])
        if len(result.candidates) != 1:
            raise ProviderUnavailable("Gemini did not return the expected fictional candidate.")
        candidate = result.candidates[0]
        if (
            candidate.field_id != "FIELD_0001"
            or candidate.value != "2028-12-31"
            or candidate.evidence.source_id != "email"
            or candidate.evidence.quote not in sanitized["sources"][0]["text"]
        ):
            raise ProviderUnavailable("Gemini failed the fictional value or evidence check.")
        print("Anymize to Gemini extraction passed using sanitized evidence only.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr", action="store_true", help="Also test the PDF endpoint with a generated PDF.")
    parser.add_argument("--with-gemini", action="store_true", help="Also extract a date from sanitized evidence.")
    args = parser.parse_args()
    try:
        check(get_settings(), ocr=args.ocr, with_gemini=args.with_gemini)
    except ProviderUnavailable as exc:
        print(str(exc))
        raise SystemExit(1) from None
    except (ValueError, KeyError, TypeError):
        print("Provider returned an unexpected fictional result; check failed.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
