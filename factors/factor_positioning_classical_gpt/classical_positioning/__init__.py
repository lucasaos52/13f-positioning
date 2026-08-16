"""Classical factor positioning from point-in-time 13F holdings.

The package deliberately separates measurement (manager exposures and
crowding state) from directional hypotheses (factor rotation and funding
flow).  Static crowding is retained as a placebo/risk state, not promoted to
an alpha signal by construction.
"""

from .config import ResearchConfig
from .pit import PITQuarterStore

__all__ = ["ResearchConfig", "PITQuarterStore"]
