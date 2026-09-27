"""The pickup blend's point, shared by the published forecast and the recalibration.

Pickup (Weatherford and Kimes 2003) is this year's count plus the entries the
family's last edition still took after the same horizon. Inside
PICKUP_HORIZON days the model's point is averaged with it in log space,
PICKUP_WEIGHT to the model. forecast.pickup applies the blend to the
published forecast; model.recalibration centres the residuals it sizes the
range from on the same point, so the range fits the forecast the site
publishes (#191).
"""
import math

PICKUP_HORIZON = 14
PICKUP_WEIGHT = 0.5


def pickup_blend(point, pickup, days_to_start):
    """The model's point averaged with pickup in log space, or None outside the blend."""
    if not (pickup and pickup > 0 and point > 0 and 0 < days_to_start <= PICKUP_HORIZON):
        return None
    return math.exp(PICKUP_WEIGHT * math.log(point) + (1 - PICKUP_WEIGHT) * math.log(pickup))
