from distutils.version import LooseVersion
import sys
import asyncssh


if sys.version_info < (3, 6):
    raise RuntimeError("Only Python 3.6+ is supported.")

if LooseVersion(asyncssh.__version__) < LooseVersion("1.16"):
    raise RuntimeError("asyncssh >= 1.16 is required. Please upgrade asyncssh.")

# Entrypoint
from gpustat_web.__main__ import main as main
