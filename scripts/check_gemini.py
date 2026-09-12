"""Connectivity check using only hard-coded, fictional evidence; never reads supplier files."""

from nova.config import get_settings
from nova.providers import Gemini, ProviderUnavailable

settings = get_settings()
try:
    result = Gemini(settings).evaluate(
        [{"field_id": "FIELD_0001", "label": "Certificate expiry date", "field_type": "Date", "rules": {}}],
        [{"source_id": "email", "text": "The certificate expires on 31 December 2028."}],
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].value == "2028-12-31"
    assert result.candidates[0].evidence.quote in "The certificate expires on 31 December 2028."
    print("Gemini connection and structured evidence extraction passed with fictional data.")
except (ProviderUnavailable, AssertionError) as exc:
    print(
        str(exc)
        if isinstance(exc, ProviderUnavailable)
        else "Gemini returned an unexpected synthetic result."
    )
    raise SystemExit(1) from None
