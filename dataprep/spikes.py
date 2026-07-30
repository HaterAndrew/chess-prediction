"""Early-bird spike detection (01_data_prep, verbatim)."""
import pandas as pd


def annotate_spikes(summary, daily_counts):
    print("\nDetecting early-bird spikes...")

    spike_results = []
    for tid, group in daily_counts.groupby('tid'):
        window = group[(group['T'] >= 55) & (group['T'] <= 75)]
        baseline_region = group[(group['T'] >= 76) & (group['T'] <= 90)]

        if len(window) == 0 or len(baseline_region) == 0:
            spike_results.append({'tid': tid, 'early_bird_spike': False, 'spike_day': None, 'spike_magnitude': 0})
            continue

        baseline_rate = max(baseline_region['daily_regs'].median(), 1)
        peak_idx = window['daily_regs'].idxmax()
        peak_row = window.loc[peak_idx]
        magnitude = peak_row['daily_regs'] / baseline_rate

        spike_results.append({
            'tid': tid,
            'early_bird_spike': magnitude >= 5,
            'spike_day': int(peak_row['T']),
            'spike_magnitude': round(magnitude, 1)
        })

    spike_results = pd.DataFrame(spike_results)
    summary = summary.merge(spike_results, on='tid', how='left')
    summary['early_bird_spike'] = summary['early_bird_spike'].fillna(False)

    n_spikes = summary['early_bird_spike'].sum()
    print(f"  {n_spikes} tournaments with detected early-bird spikes")
    return summary, n_spikes
