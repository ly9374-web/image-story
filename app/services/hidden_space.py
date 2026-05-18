from __future__ import annotations


HIDDEN_PASSCODE = "ly123"


def is_valid_passcode(passcode: str) -> bool:
    return str(passcode or "").strip() == HIDDEN_PASSCODE


def unlock(current_unlocked: bool, passcode: str) -> bool:
    if current_unlocked:
        return True
    return is_valid_passcode(passcode)

