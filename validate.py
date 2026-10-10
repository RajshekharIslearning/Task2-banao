"""Independent checks of the agent's work. Run from the project root:
    python validate.py            (files only)
    python validate.py --live     (also tests the running server, default http://127.0.0.1:5000)
Needs: pandas. Does not trust the agent's own tests."""
import sys, re, json, glob, urllib.request, urllib.error, math
from pathlib import Path
import pandas as pd

BASE = next((a for a in sys.argv[1:] if a.startswith('http')), 'http://127.0.0.1:8000')
LIVE = '--live' in sys.argv
res = []
def check(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (f'  -> {detail}' if detail else ''))

def rd(p, **k): return pd.read_csv(p, **k)

# ---- 1. predictions.csv ----
try:
    ss, te, pr = rd('data/sample_submission.csv'), rd('data/test_unlabelled.csv'), rd('predictions.csv')
    check('predictions columns match sample_submission', list(pr.columns) == list(ss.columns), str(list(pr.columns)))
    check('row count equals test file', len(pr) == len(te), f'{len(pr)} vs {len(te)}')
    check('order_ids unique', pr.order_id.is_unique)
    check('order_ids match test set', set(pr.order_id) == set(te.order_id))
    sc = pr[pr.columns[1]]
    check('scores numeric, finite, no blanks', pd.api.types.is_numeric_dtype(sc) and sc.notna().all() and all(math.isfinite(x) for x in sc))
    check('scores not constant', sc.nunique() > 100, f'{sc.nunique()} distinct')
    m = pr.merge(te, on='order_id')
    cod, non = m[m.payment_mode == 'cod'][pr.columns[1]].mean(), m[m.payment_mode != 'cod'][pr.columns[1]].mean()
    check('COD orders score higher than prepaid (known real signal)', cod > non, f'cod {cod:.3f} vs other {non:.3f}')
    check('average score is near the ~11% base rate (0.05 to 0.25)', 0.05 < sc.mean() < 0.25, f'{sc.mean():.3f}')
except Exception as e:
    check('predictions.csv readable', False, repr(e))

# ---- 2. leakage guard: leaky columns must not be model inputs ----
src = ''
for f in glob.glob('app/**/*.py', recursive=True) + glob.glob('train.py'):
    src += '\n' + Path(f).read_text(errors='ignore')
bad = []
for col in ['last_service_event_type', 'pickup_scheduled_at']:
    for m_ in re.finditer(col, src):
        line = src[src.rfind('\n', 0, m_.start()) + 1: src.find('\n', m_.end())]
        bad.append(line.strip())
print('INFO lines mentioning leaky columns (read each; must be exclusion/warning/leak-experiment only):')
for b in bad[:12]: print('     ', b[:140])
check('leaky columns appear in code only in few lines (manual read above)', len(bad) <= 15, f'{len(bad)} lines')

# ---- 3. housekeeping ----
gi = Path('.gitignore').read_text() if Path('.gitignore').exists() else ''
check('data/ is gitignored', re.search(r'^/?data/?\s*$', gi, re.M) is not None)
for f in ['README.md', 'memo.md', 'submission-form.md', 'DECISIONS.md', 'requirements.txt', 'train.py', 'RECORDING_SCRIPT.md']:
    check(f'{f} exists', Path(f).exists())
if Path('memo.md').exists():
    words = len(re.findall(r'\w+', Path('memo.md').read_text()))
    check('memo is about one page (330 to 450 words)', 330 <= words <= 450, f'{words} words')
    heads = [h for h in ['The decision', 'The number', 'The rupees', 'What to do next week'] if h.lower() in Path('memo.md').read_text().lower()]
    check('memo has the four required headings', len(heads) == 4, str(heads))
    jar = [w for w in ['AUC', 'precision', 'recall', 'logistic', 'gradient'] if w.lower() in Path('memo.md').read_text().lower()]
    check('memo free of jargon', not jar, str(jar))
if Path('submission-form.md').exists():
    t = Path('submission-form.md').read_text()
    left = len(re.findall(r'TODO|TBD|<fill|\[ *\]|XXX|\.\.\.\.', t))
    print(f'INFO form markers still to fill by you: {left}')
if Path('evidence/metrics.json').exists():
    j = json.loads(Path('evidence/metrics.json').read_text()); print('INFO metrics.json keys:', list(j)[:12])

# ---- 4. live server ----
def call(path, data=None):
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read() or b'{}')
        except Exception: body = {}
        return e.code, body
    except Exception as e:
        return 0, {'error': repr(e)}

if LIVE:
    s, _ = call('/health'); check('GET /health returns 200', s == 200, str(s))
    te = rd('data/test_unlabelled.csv', dtype={'delivery_pincode': str}); cu = rd('data/customers.csv')
    row = te.iloc[0].to_dict(); row = {k: (None if pd.isna(v) else v) for k, v in row.items()}
    row.pop('order_id', None)
    s, r = call('/predict', row); check('valid order returns 200', s == 200, str(s))
    check('response has score, action, reasons', all(k in r for k in ['score', 'recommended_action', 'reasons']), str(list(r)))
    if 'score' in r: check('score between 0 and 1', 0 <= float(r['score']) <= 1, str(r['score']))
    rs = ' '.join(r.get('reasons', [])) if isinstance(r.get('reasons'), list) else str(r.get('reasons'))
    check('reasons read as plain English (no feature codes)', not re.search(r'\b(cod|ch_|fam_|prior_rate|z-score|coef)\b|=\s*\d|[+]\d\.\d', rs), rs[:160])
    bad_row = dict(row); bad_row.pop('sku', None); s, _ = call('/predict', bad_row); check('missing field returns 400, not 500', s == 400, str(s))
    unk = dict(row); unk['sku'] = 'NOPE-000'; s, _ = call('/predict', unk); check('unknown SKU does not crash', s in (200, 400, 422), str(s))
    leak = dict(row); leak['last_service_event_type'] = 'REVERSE_PICKUP'; leak['pickup_scheduled_at'] = '2026-09-01T10:00:00'
    s1, a = call('/predict', row); s2, b = call('/predict', leak)
    check('leaky fields do not change the score', s2 == 200 and abs(float(a['score']) - float(b['score'])) < 1e-9, f"{a.get('score')} vs {b.get('score')}")
    ids = cu[cu.shield_member == 'Y'].customer_id.head(25).tolist(); worst = None
    acts = set()
    for cid in ids:
        o = dict(row); o['customer_id'] = cid; o['payment_mode'] = 'cod'; o['promised_delivery_days'] = 12; o['discount_pct'] = 25
        s, x = call('/predict', o); acts.add(x.get('recommended_action'))
    check('Shield customers never get a hold action', not any('hold' in str(a_).lower() for a_ in acts), str(acts))
    o = dict(row); o['payment_mode'] = 'prepaid_card'; o['customer_prior_returns'] = 0; o['discount_pct'] = 0
    o2 = dict(o); o2['payment_mode'] = 'cod'; o2['customer_prior_returns'] = 3
    _, lo = call('/predict', o); _, hi = call('/predict', o2)
    check('risky order scores higher than safe one', float(hi.get('score', 0)) > float(lo.get('score', 1)), f"{hi.get('score')} vs {lo.get('score')}")
    jan = dict(row); jan['order_placed_at'] = '2025-10-15T12:00:00'; jan['order_value_inr'] = float(row['order_value_inr']) * 100
    _, n = call('/predict', jan); _, n0 = call('/predict', dict(row, order_placed_at='2025-10-15T12:00:00'))
    check('x100 October value gives about the same score as the real value', abs(float(n.get('score', 9)) - float(n0.get('score', 0))) < 0.02, f"{n.get('score')} vs {n0.get('score')}")
else:
    print('INFO live checks skipped (start the server, then run: python validate.py --live)')

print(f"\n{sum(res)}/{len(res)} checks passed")
sys.exit(0 if all(res) else 1)
