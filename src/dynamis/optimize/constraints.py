"""Safety limits = the optimizer's constraint set (ARCHITECTURE 10.3).

Box limits (lambda band, boost ceiling, spark authority) also keep the search inside the
surrogate's trained domain, where uncertainty is low. The knock-margin floor is a true
inequality constraint enforced via penalty, made conservative by `sigma_k` (subtract
that many ensemble sigmas from the predicted margin).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyLimits:
    knock_margin_min: float = 0.10   # require predicted knock margin >= this
    lam_min: float = 0.78            # rich power band (also surrogate domain)
    lam_max: float = 1.00
    boost_min_bar: float = 0.3
    boost_max_bar: float = 1.8       # hardware/turbo ceiling (<= surrogate domain 2.0)
    spark_min: float = 5.0
    spark_max: float = 26.0
    sigma_k: float = 1.0             # conservatism: margin_eff = margin - sigma_k * sigma
