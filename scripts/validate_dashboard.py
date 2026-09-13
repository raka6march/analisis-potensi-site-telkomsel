"""Reconcile dashboard metrics and historical class labels with a site-month CSV."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('docs/validation/dashboard_validation.json'))
    args = parser.parse_args()
    df = pd.read_csv(args.csv, dtype={'site_id': 'string', 'month': 'string'})
    cats = ['payload', 'digital', 'games', 'video']
    assert not df.isna().any().any(), 'Missing values'
    assert not df.duplicated(['site_id', 'month']).any(), 'Duplicate site-month'
    numeric = df.select_dtypes(include='number')
    assert np.isfinite(numeric.to_numpy()).all() and numeric.ge(0).all().all()
    dates = pd.to_datetime(df.month, format='%Y-%m-%d')
    assert df.days_observed.gt(0).all()
    assert np.allclose(df.calendar_coverage, df.days_observed / dates.dt.days_in_month)
    assert df.site_coverage_available.between(0, 1).all()
    assert df.calendar_coverage.between(0, 1).all()
    report = {
        'source': args.csv.name,
        'source_sha256': hashlib.sha256(args.csv.read_bytes()).hexdigest(),
        'site_month_rows': len(df), 'distinct_sites': int(df.site_id.nunique()),
        'month_count': int(df.month.nunique()), 'duplicate_site_months': 0,
        'missing_cells': 0, 'categories': {}, 'monthly_coverage': [],
        'method': 'Fixed global tertiles over all site-month daily averages; not a predictive model',
    }
    november = df[df.month.eq('2023-11-01')]
    assert november.site_id.nunique() == 71394, 'November population differs from screenshots'
    expected = {
        'payload': ([24250, 23723, 23421], 797.12, [293.24, 805.65, 1533.70]),
        'digital': ([22463, 23288, 25643], 38.61, [13.19, 36.90, 76.55]),
        'games': ([19855, 24735, 26804], 225.52, [17.12, 180.16, 605.45]),
        'video': ([19234, 23474, 28686], 379.47, [41.49, 292.39, 906.63]),
    }
    for cat in cats:
        metric, label = cat + '_user_daily_avg', cat + '_kelas'
        lo, hi = df[metric].quantile([1 / 3, 2 / 3])
        classes = ['Rendah', 'Sedang', 'Tinggi']
        computed = pd.cut(df[metric], [-np.inf, lo, hi, np.inf], labels=classes)
        assert computed.eq(df[label]).all(), f'{cat}: class mismatch'
        counts = november.groupby(label).site_id.nunique().reindex(classes)
        medians = november.groupby(label)[metric].median().reindex(classes)
        assert counts.tolist() == expected[cat][0]
        assert round(float(november[metric].median()), 2) == expected[cat][1]
        assert [round(float(v), 2) for v in medians] == expected[cat][2]
        assert int(counts.sum()) == len(november)
        report['categories'][cat] = {
            'threshold_low_max': float(lo), 'threshold_medium_max': float(hi),
            'class_mismatches': 0,
            'november_2023': {
                'sites': int(len(november)), 'median': float(november[metric].median()),
                'high_share': float(counts['Tinggi'] / len(november)),
                'counts': {k: int(v) for k, v in counts.items()},
                'class_medians': {k: float(v) for k, v in medians.items()},
            },
        }
    for month, part in df.groupby('month'):
        report['monthly_coverage'].append({
            'month': month[:7], 'sites': int(part.site_id.nunique()),
            'min_days_observed': int(part.days_observed.min()),
            'max_days_observed': int(part.days_observed.max()),
            'max_calendar_coverage': float(part.calendar_coverage.max()),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'PASS: {len(df):,} site-month rows, four categories and November screenshots reconciled.')


if __name__ == '__main__':
    main()
