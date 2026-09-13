"""Conservative validation of optional spelling suggestions; never auto-apply them."""

import re
from difflib import SequenceMatcher


def eligible_correction(field, original, corrected, source):
    if field.data["Field Type"] != "Freetext" or field.rules.get("options"):
        return False
    if original == corrected or original not in source:
        return False
    # Preserve all non-word characters, numbers, and redaction/field identifiers.
    if re.findall(r"\W+|\d+|\b[A-Z_]+\b", original) != re.findall(r"\W+|\d+|\b[A-Z_]+\b", corrected):
        return False
    words, replacements = re.findall(r"\w+", original), re.findall(r"\w+", corrected)
    if len(words) != len(replacements):
        return False
    for before, after in zip(words, replacements):
        if before == after:
            continue
        if not before.islower() or not after.islower() or min(len(before), len(after)) < 4:
            return False
        if SequenceMatcher(None, before, after).ratio() < 0.7:
            return False
    return True
