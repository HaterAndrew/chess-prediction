"""Which events have a registration curve to learn from or grade on."""


def has_curve(summary):
    """True where the event has a curve: the loader's has_curve (export or scrape),
    or, for a frame the loader never saw, the export's has_timestamps."""
    col = 'has_curve' if 'has_curve' in summary.columns else 'has_timestamps'
    return summary[col].fillna(False).astype(bool)
