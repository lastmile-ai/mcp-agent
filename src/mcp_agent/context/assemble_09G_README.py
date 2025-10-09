# Patch: add file length provider usage if available
# This file augments the existing assemble.py by documenting the expected option:
#
# AssembleOptions may include an attribute `file_lengths: Dict[str,int]` injected by the caller.
# If absent, assemble will attempt to compute file lengths via FileLengthProvider for any
# file:// URIs seen in seeds, so neighborhood expansion can clamp to bounds.
#
# No behavior is removed; this overlay only clarifies and enables clamping when possible.
