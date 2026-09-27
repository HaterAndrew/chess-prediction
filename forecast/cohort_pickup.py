"""What each recalibration-cohort event's last edition took after each short horizon.

Inside two weeks the published point is the model's averaged with pickup
(forecast.pickup), so the recalibration sizes the range around that blend
(#191). Pickup is the event's own count plus a gain: its last edition's
final less that edition's count the same days out. The last edition is the
one the card lists last (sitebuild.editions), aliases included.
"""
from corpus.edition_counts import edition_counts_from
from sitebuild.editions import prior_editions
from tournament_aliases import FAMILY_ALIASES


def last_edition(summary, family, year):
    """The family's last finished edition before `year`, as the card finds it, or None."""
    prior = prior_editions(summary, [family] + FAMILY_ALIASES.get(family, []), year,
                           lambda fam, yr: True)
    prior = prior[prior['final_count'].notna()]
    return None if prior.empty else prior.iloc[-1]


def pickup_gains(cohort, summary, daily, horizons):
    """{(tid, T): last final - last edition's count T days out} where both are known."""
    counts = edition_counts_from(summary, daily)
    gains = {}
    for _, row in cohort.iterrows():
        last = last_edition(summary, row['family'], int(row['tournament_year']))
        if last is None:
            continue
        for T in horizons:
            seen = counts.count(last['tid'], T)
            if seen.count is not None:
                gains[(row['tid'], T)] = int(last['final_count']) - seen.count
    return gains
