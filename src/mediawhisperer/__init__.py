"""MediaWhisperer: compile your podcast and video feeds into a digest.

Pull the latest from the podcasts and channels you follow, condense each item
into skimmable notes, and stitch those notes into a single listen-ready script
you can turn into your own daily briefing.
"""

from .config import Config
from .pipeline import Pipeline, RunResult

__version__ = "0.1.0"
__all__ = ["Config", "Pipeline", "RunResult", "__version__"]
