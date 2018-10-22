import sys

if sys.version_info < (3, 6):
    raise RuntimeError("Only Python 3.6+ is supported.")
