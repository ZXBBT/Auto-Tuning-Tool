"""Engine parameter sets.

All geometry in SI units. Efficiency / combustion / knock parameters are *initial
estimates* (literature-typical) and are exactly the `theta_phys` the calibration step
(M3) will fit to real WOT logs. Treat the numbers here as priors, not ground truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EngineParams:
    """Physical + initial-estimate parameters for one engine platform."""

    name: str
    num_cylinders: int
    bore_m: float
    stroke_m: float
    conrod_m: float
    compression_ratio: float

    # --- thermodynamic / efficiency (theta_phys; calibratable) ---
    eta_thermal_base: float = 0.37   # indicated thermal efficiency at MBT
    eta_combustion: float = 0.97     # combustion completeness
    fmep_pa: float = 1.5e5           # friction mean effective pressure [Pa]

    # --- volumetric efficiency model (theta_phys; calibratable) ---
    ve_peak: float = 0.92
    ve_rpm_peak: float = 4500.0
    ve_rpm_width: float = 2600.0
    ve_floor: float = 0.70

    # --- fuel ---
    afr_stoich: float = 14.7         # gasoline
    fuel_lhv: float = 44.0e6         # lower heating value [J/kg]
    evap_cooling_k: float = 310.0    # DI charge cooling: K per (fuel/air mass ratio)

    # --- combustion timing / burn ---
    mbt_base_deg: float = 22.0       # MBT spark at low load [deg BTDC]
    mbt_k_load: float = 3.0          # deg lost per bar of boost above atmospheric
    mbt_k_rpm: float = 1.5           # deg gained per 1000 rpm above 3000
    burn_duration_deg: float = 50.0
    wiebe_a: float = 5.0
    wiebe_m: float = 2.0
    ivc_atdc_deg: float = -140.0     # intake valve closing [deg ATDC compression]

    # --- knock: Douaud-Eyzat ignition delay + Livengood-Wu (theta_phys) ---
    knock_A: float = 17.68           # [ms]
    knock_a_on: float = 3.402        # octane exponent
    knock_n_p: float = 1.7           # pressure exponent
    knock_B: float = 3800.0          # activation temperature [K]
    gamma_unburned: float = 1.33     # end-gas polytropic index

    # --- spark efficiency ---
    spark_eff_k: float = 0.0015      # torque-loss curvature per deg^2 of retard

    # -------- derived geometry --------
    @property
    def piston_area_m2(self) -> float:
        return math.pi * self.bore_m ** 2 / 4.0

    @property
    def cyl_displacement_m3(self) -> float:
        return self.piston_area_m2 * self.stroke_m

    @property
    def displacement_m3(self) -> float:
        return self.cyl_displacement_m3 * self.num_cylinders

    @property
    def clearance_volume_m3(self) -> float:
        return self.cyl_displacement_m3 / (self.compression_ratio - 1.0)

    @property
    def crank_radius_m(self) -> float:
        return self.stroke_m / 2.0


# VAG EA888 Gen3 2.0T (MK7 GTI). Geometry is real; non-geometry params are priors.
EA888_GEN3 = EngineParams(
    name="VAG EA888 Gen3 2.0T (MK7 GTI)",
    num_cylinders=4,
    bore_m=0.0825,
    stroke_m=0.0928,
    conrod_m=0.144,
    compression_ratio=9.6,
)
