import argparse
import re
from pathlib import Path
from typing import Dict, Any

# Helpers -----------------------------------------------------

def _parse_table(lines, header_regex, row_regex, key_fn=None, value_fns=None, stop_regex=None):
    data = {}
    in_section = False
    for line in lines:
        if stop_regex and re.match(stop_regex, line):
            if in_section:
                break
        if not in_section:
            if re.match(header_regex, line):
                in_section = True
            continue
        m = re.match(row_regex, line)
        if m:
            key = key_fn(m) if key_fn else m.group(1)
            vals = value_fns(m) if value_fns else m.groups()[1:]
            data[key] = vals
    return data

# Parse key metrics -------------------------------------------

def parse_report(path: Path) -> Dict[str, Any]:
    text = path.read_text()
    lines = text.splitlines()

    def find_metric(patterns):
        for pat in patterns:
            m = re.search(pat, text, re.M)
            if m:
                return float(m.group(1))
        return None

    out: Dict[str, Any] = {}
    out['bb_per_100'] = find_metric([r'^bb/100_net\s*\|\s*([\-0-9\.]+)'])
    out['vpip'] = find_metric([
        r'^vpip_pct\s*\|\s*([0-9\.]+)',
        r'^vpip\s*\|\s*([0-9\.]+)\s*$',
    ])
    out['flop_reach'] = find_metric([r'^flop_reach\s*\|\s*([0-9\.]+)'])

    # BB vs Open by Position
    pos_tbl = _parse_table(
        lines,
        header_regex=r'^== BB vs Open by Position',
        row_regex=r'^(BU|SB|OTHERS)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|',
        key_fn=lambda m: m.group(1),
        value_fns=lambda m: {
            'fold': int(m.group(2)),
            'call': int(m.group(3)),
            '3bet': int(m.group(4)),
        },
        stop_regex=r'^==|^\s*$'
    )
    if pos_tbl:
        out['bb_vs_open_pos'] = {}
        for k,v in pos_tbl.items():
            tot = v['fold']+v['call']+v['3bet']
            out['bb_vs_open_pos'][k] = {
                'fold': v['fold']/tot if tot else 0,
                'call': v['call']/tot if tot else 0,
                '3bet': v['3bet']/tot if tot else 0,
                'n': tot,
            }

    # BB vs Open by Size
    size_tbl = _parse_table(
        lines,
        header_regex=r'^== BB vs Open by Size',
        row_regex=r'^(\d\.\d-\d\.\d)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|',
        key_fn=lambda m: m.group(1),
        value_fns=lambda m: {
            'fold': int(m.group(2)),
            'call': int(m.group(3)),
            '3bet': int(m.group(4)),
        },
        stop_regex=r'^==|^\s*$'
    )
    if size_tbl:
        out['bb_vs_open_size'] = {}
        for k,v in size_tbl.items():
            tot = v['fold']+v['call']+v['3bet']
            out['bb_vs_open_size'][k] = {
                'fold': v['fold']/tot if tot else 0,
                'call': v['call']/tot if tot else 0,
                '3bet': v['3bet']/tot if tot else 0,
                'n': tot,
            }

    # Defense vs Price
    def_price_tbl = _parse_table(
        lines,
        header_regex=r'^== Defense vs Price',
        row_regex=r'^(0-0\.20|0\.20-0\.33|0\.33-0\.50)\s*\|\s*(\d+)\s*\|\s*([0-9\.]+)\s*\|\s*([0-9\.]+)\s*\|\s*([0-9\.]+)\s*\|\s*([\-0-9\.]+)',
        key_fn=lambda m: m.group(1),
        value_fns=lambda m: {
            'facing': int(m.group(2)),
            'mdf_avg': float(m.group(3)),
            'mdf_adj': float(m.group(4)),
            'defend_rate': float(m.group(5)),
            'gap_adj': float(m.group(6)),
        },
        stop_regex=r'^Defense vs Price by street'
    )
    if def_price_tbl:
        out['def_vs_price'] = def_price_tbl

    return out


def diff_metric(v5, cur):
    delta = lambda a,b: None if a is None or b is None else b-a
    return {
        'bb_per_100': delta(v5.get('bb_per_100'), cur.get('bb_per_100')),
        'vpip': delta(v5.get('vpip'), cur.get('vpip')),
        'flop_reach': delta(v5.get('flop_reach'), cur.get('flop_reach')),
    }

def diff_table(v5_table, cur_table):
    out = {}
    if not v5_table or not cur_table:
        return out
    keys = set(v5_table).intersection(cur_table)
    for k in keys:
        v = v5_table[k]
        c = cur_table[k]
        out[k] = {
            'fold': c['fold'] - v['fold'],
            'call': c['call'] - v['call'],
            '3bet': c['3bet'] - v['3bet'],
            'n_v5': v.get('n'),
            'n_cur': c.get('n'),
        }
    return out

def diff_def_price(v5_table, cur_table):
    """
    Specialized diff for Defense vs Price table.
    We only care about defend_rate (and sample size) per bucket.
    """
    out = {}
    if not v5_table or not cur_table:
        return out
    keys = set(v5_table).intersection(cur_table)
    for k in keys:
        v = v5_table[k]; c = cur_table[k]
        out[k] = {
            'defend_rate': c.get('defend_rate',0) - v.get('defend_rate',0),
            'n_v5': v.get('facing'), 'n_cur': c.get('facing'),
            'mdf_gap': c.get('mdf_adj',0) - v.get('mdf_adj',0),
        }
    return out


def avg_reports(paths):
    agg: Dict[str, list] = {}
    for p in paths:
        d = parse_report(Path(p))
        for k,v in d.items():
            agg.setdefault(k, []).append(v)
    out = {}
    for k,vals in agg.items():
        if k == 'def_vs_price':
            merged = {}
            keys = set().union(*[v.keys() for v in vals if isinstance(v, dict)])
            for key in keys:
                facing = mdf_avg = mdf_adj = defend_rate = gap_adj = cnt = 0
                for v in vals:
                    if not isinstance(v, dict) or key not in v:
                        continue
                    row = v[key]
                    facing += row.get('facing', 0)
                    mdf_avg += row.get('mdf_avg', 0)
                    mdf_adj += row.get('mdf_adj', 0)
                    defend_rate += row.get('defend_rate', 0)
                    gap_adj += row.get('gap_adj', 0)
                    cnt += 1
                if cnt:
                    merged[key] = {
                        'facing': facing / cnt,
                        'mdf_avg': mdf_avg / cnt,
                        'mdf_adj': mdf_adj / cnt,
                        'defend_rate': defend_rate / cnt,
                        'gap_adj': gap_adj / cnt,
                    }
            out[k] = merged
        elif isinstance(vals[0], dict):
            merged = {}
            keys = set().union(*[v.keys() for v in vals if isinstance(v,dict)])
            for key in keys:
                fold=call=three=n=0; cnt=0
                for v in vals:
                    if not isinstance(v,dict): continue
                    if key not in v: continue
                    fold += v[key].get('fold',0); call += v[key].get('call',0); three += v[key].get('3bet',0); n += v[key].get('n',0); cnt+=1
                if cnt:
                    merged[key] = {
                        'fold': fold/cnt,
                        'call': call/cnt,
                        '3bet': three/cnt,
                        'n': n/cnt,
                    }
            out[k]=merged
        else:
            out[k]= sum(v for v in vals if v is not None)/len([v for v in vals if v is not None])
    return out


def _read_baseline_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    out: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--v5', nargs='+', help='v5v report.txt paths')
    ap.add_argument('--baseline-file', default='notes/baseline_v5v.txt',
                    help='baseline file listing v5v report.txt paths')
    ap.add_argument('--cur', nargs='+', required=True, help='current report.txt paths')
    args = ap.parse_args()

    v5_paths = args.v5
    if not v5_paths:
        v5_paths = _read_baseline_file(Path(args.baseline_file))
    if not v5_paths:
        ap.error('missing --v5 and baseline file is empty or not found')

    v5 = avg_reports(v5_paths)
    cur = avg_reports(args.cur)

    print('METRIC DIFF (cur - v5):', diff_metric(v5,cur))
    print('\nBB vs open by position diff (fold/call/3bet):')
    for pos, row in diff_table(v5.get('bb_vs_open_pos'), cur.get('bb_vs_open_pos')).items():
        print(pos, {k: round(row[k],3) for k in ('fold','call','3bet')}, 'n_v5', row['n_v5'], 'n_cur', row['n_cur'])
    print('\nBB vs open by size diff:')
    for sz, row in diff_table(v5.get('bb_vs_open_size'), cur.get('bb_vs_open_size')).items():
        print(sz, {k: round(row[k],3) for k in ('fold','call','3bet')}, 'n_v5', row['n_v5'], 'n_cur', row['n_cur'])
    print('\nDefense vs price diff:')
    for bucket, row in diff_def_price(v5.get('def_vs_price'), cur.get('def_vs_price')).items():
        print(bucket,
              {'defend_rate': round(row['defend_rate'],3),
               'mdf_gap': round(row['mdf_gap'],3)},
              'n_v5', row['n_v5'], 'n_cur', row['n_cur'])

if __name__ == '__main__':
    main()
