"""fit_models: everything the live forecasts read, fitted in one place."""
from model.core import N5v4_Final
from model.curves import build_template_curves
from ratio_model import build_ratio_model
from shared.curves import has_curve
from shared.season import CURRENT_SEASON

from forecast.cohort_pickup import pickup_gains
from forecast.new_event import new_event_prior
from forecast.pickup import PICKUP_HORIZON
from forecast.types import Fitted
from forecast.yoy_range import yoy_arms

# Recalibration needs at least this many finished events in its cohort.
MIN_RECAL_EVENTS = 5
# The recalibration's horizons inside the pickup blend.
RECAL_PICKUP_HORIZONS = tuple(T for T in (14, 7, 3, 1) if T <= PICKUP_HORIZON)
# Events smaller than this are left out of the recalibration cohort.
MIN_RECAL_FINAL = 50


def _in_person(summary):
    return summary[(~summary['is_online'].fillna(False)) &
                   (~summary['is_covid'].fillna(False))]


def recal_cohort(summary, completed_tids, season):
    """The two seasons before this one, plus this season's finished events."""
    rows = _in_person(summary)
    return rows[
        has_curve(rows) &
        (rows['final_count'] >= MIN_RECAL_FINAL) &
        (rows['tournament_year'].isin([season - 2, season - 1]) |
         rows['tid'].isin(completed_tids))
    ].copy()


def settled_editions(train, completed_tids, season):
    """Editions whose final is final: earlier seasons, and this season's finished events."""
    return train[(train['tournament_year'] < season) | train['tid'].isin(completed_tids)]


def fit_models(summary, daily, enrichment_lookup, completed_tids, season=None,
               standings=None, verbose=True):
    """Fit the nowcast model, recalibrate it, and build the ratio model, the curves,
    the year-over-year spread and the new-event prior.

    completed_tids are this season's finished events; they train alongside
    the earlier seasons. standings is the historical standings frame the fit
    joins (None: the file on disk); verbose=False drops the standings-join
    report. The Fitted's recal holds the cohort size and the
    recalibration diagnostics, which are None when the cohort was too small.
    """
    season = CURRENT_SEASON if season is None else season
    completed = completed_tids if completed_tids else None
    train = _in_person(summary)

    model = N5v4_Final()
    model.fit(train[has_curve(train)], daily, enrichment_lookup=enrichment_lookup,
              completed_tids=completed, season=season, standings=standings,
              verbose_standings_join=verbose,
              all_summary_families=set(summary['family'].dropna().unique()))

    cohort = recal_cohort(summary, completed_tids or set(), season)
    recal = {'diag': None, 'n': len(cohort),
             'n_season': int((cohort['tournament_year'] == season).sum())}
    if len(cohort) >= MIN_RECAL_EVENTS:
        # regime_year: the cohort holds this season's finished events, so the
        # bias correction fits on them.
        # pickup_gains: inside two weeks the widths are sized around the
        # pickup blend the site publishes (#191).
        gains = pickup_gains(cohort, summary, daily, RECAL_PICKUP_HORIZONS)
        recal['diag'] = model.recalibrate(cohort, daily, regime_year=season,
                                          pickup_gains=gains)

    settled = settled_editions(train, completed_tids or set(), season)
    return Fitted(model=model,
                  ratios=build_ratio_model(train, daily, completed_tids=completed, season=season),
                  curves=build_template_curves(train, daily, season=season),
                  recal=recal, yoy_arms=yoy_arms(settled),
                  new_event_prior=new_event_prior(settled))
