"""The pickup forecast, and its blend with the model inside two weeks.

Pickup (Weatherford and Kimes 2003): this year's count plus the entries the
family's last edition still took after the same horizon, c_T + (F_last - c_last,T).
Inside PICKUP_HORIZON days the model's point is averaged with it in log space,
PICKUP_WEIGHT to the model, and the range moves with the point. On the
walk-forward, a weight chosen on earlier seasons only settled on 0.5 for each
of 2024, 2025 and 2026, and lowered the short-horizon interval and point
scores in all three; at T-28 and beyond no weight helped, so those horizons
keep the model alone.
"""
import math

PICKUP_HORIZON = 14
PICKUP_WEIGHT = 0.5


def pickup_point(count, T, prior, count_of):
    """count + (last final - last edition's count at T), or None when that count is unknown.

    prior: the family's finished editions before this one, oldest first.
    count_of(tid, T) reads an edition's count as of T days out (a CountAsOf).
    """
    if prior.empty:
        return None
    last = prior.iloc[-1]
    seen = count_of(last['tid'], T)
    if seen.count is None:
        return None
    return int(count + int(last['final_count']) - seen.count)


def blend_pickup(forecast, obs):
    """The model's forecast averaged with pickup in log space, inside PICKUP_HORIZON days.

    The range scales with the point; nothing falls below the count.
    """
    if not (obs.pickup and obs.pickup > 0 and forecast.point > 0
            and 0 < obs.days_to_start <= PICKUP_HORIZON):
        return forecast
    return forecast.moved_to(math.exp(PICKUP_WEIGHT * math.log(forecast.point)
                                      + (1 - PICKUP_WEIGHT) * math.log(obs.pickup)), obs.count)
