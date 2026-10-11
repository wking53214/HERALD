"""Where in a decision a gate sits.

A gate declares its end, so the position is a property of the gate and not a
fact about where somebody happened to call it.

ALPHA -- judged before the work runs. A failure means the work never starts.
OMEGA -- judged on the produced output. A failure means the output does not leave.

The values match the position names in CNS, so the two can be read side by side.
This module has no dependency on CNS.
"""

POSITION_ALPHA = "alpha"
POSITION_OMEGA = "omega"
