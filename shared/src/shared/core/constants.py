"""
DEPRECATED: Moved to frontend.i18n.messages

This file is kept for backward compatibility only.
"""
import warnings


def __getattr__(name):
    if name == "MESSAGES":
        warnings.warn(
            "MESSAGES has been moved to frontend.i18n.messages",
            DeprecationWarning,
            stacklevel=2,
        )
        from frontend.i18n.messages import MESSAGES
        return MESSAGES
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
