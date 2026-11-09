"""Grants and expenditure reporting pipeline.

Takes a programme spend file, checks it against named validation rules, computes the
indicators a programme office reports upward, and writes three outputs:

    output/validation_report.csv  every issue found, with the row number and the rule
    output/indicators.csv         per budget line - the feed for Power BI
    output/monthly_report.html    a one-page summary, printable to PDF

This is the work that used to be done by hand: reading the file line by line, catching
the double payments and the over-disbursements, then writing the summary. Running it
takes a second and the rules are written down, which means the next person gets the same
answer.

Standard library plus nothing. No install, runs on any machine with Python 3.

Usage:  python3 grants_pipeline.py [path/to/spend.csv]
"""
import csv, os, re, sys
from collections import defaultdict
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN = os.path.join(HERE, 'data', 'programme_spend.csv')
OUT_DIR = os.path.join(HERE, 'output')

# The reporting period. Everything is checked against this window.
PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 12, 31)
PERIOD_LABEL = '1 January to 31 December 2026'
REPORT_AS_OF = date(2026, 11, 9)

REQUIRED = ['project_code', 'project_name', 'budget_line', 'allocated_eur',
            'disbursed_eur', 'disbursement_date', 'supplier', 'invoice_ref']

# A controlled list is the difference between a report you can total and one you cannot.
VALID_CATEGORIES = {'Infrastructure', 'Services', 'Capacity building', 'Programme support'}

RULES = {
    'R1': 'Required field is empty',
    'R2': 'Duplicate invoice reference',
    'R3': 'Disbursed exceeds allocated',
    'R4': 'Disbursement dated outside the reporting period',
    'R5': 'Date cannot be read',
    'R6': 'Amount is zero or negative',
    'R7': 'Deliverable overdue and not complete',
    'R8': 'Category is outside the controlled list',
}


# ---------------------------------------------------------------- cleaning

def money(raw):
    """Parse an amount the way it actually arrives: '85,000.00', ' 32 400.00 ', '-4200'.

    Returns None when the value cannot be read, so the caller can raise R5/R6 rather
    than silently treating the row as zero - which is how bad totals get published.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(' ', '')
    s = re.sub(r'(?<=\d)[ ,](?=\d{3}\b)', '', s)   # thousands separators only
    s = s.replace(' ', '')
    if not s:
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_date(raw):
    """Accept the formats a mixed team actually types. Return None if unreadable."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def tidy(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


# ---------------------------------------------------------------- validation

def validate(rows):
    """Return (issues, clean_rows).

    An issue never silently drops a row. Rows that fail a MONETARY rule are excluded
    from the totals, because including them would misstate the report; every other
    failure is reported but the row still counts. That distinction is the whole point
    of a validation step - it says what was excluded and why.
    """
    issues = []
    seen_invoice = {}
    clean = []

    for i, r in enumerate(rows, start=2):   # start=2: row 1 is the header in the file
        row_issues = []

        for f in REQUIRED:
            if not tidy(r.get(f)):
                row_issues.append(('R1', f'{f} is empty'))

        ref = tidy(r.get('invoice_ref'))
        if ref:
            if ref in seen_invoice:
                row_issues.append(('R2', f'{ref} also appears on row {seen_invoice[ref]}'))
            else:
                seen_invoice[ref] = i

        allocated = money(r.get('allocated_eur'))
        disbursed = money(r.get('disbursed_eur'))
        monetary_fault = False

        if allocated is None:
            row_issues.append(('R5', f"allocated_eur '{r.get('allocated_eur')}' cannot be read"))
            monetary_fault = True
        if disbursed is None:
            row_issues.append(('R5', f"disbursed_eur '{r.get('disbursed_eur')}' cannot be read"))
            monetary_fault = True

        if disbursed is not None and disbursed <= 0:
            row_issues.append(('R6', f'disbursed_eur is {disbursed:.2f}'))
            monetary_fault = True

        if allocated is not None and disbursed is not None and disbursed > allocated:
            over = disbursed - allocated
            row_issues.append(('R3', f'over by EUR {over:,.2f} ({disbursed / allocated:.0%} of allocation)'))
            monetary_fault = True

        d_date = parse_date(r.get('disbursement_date'))
        if r.get('disbursement_date') and d_date is None:
            row_issues.append(('R5', f"disbursement_date '{r.get('disbursement_date')}' cannot be read"))
            monetary_fault = True
        elif d_date and not (PERIOD_START <= d_date <= PERIOD_END):
            row_issues.append(('R4', f'dated {d_date.isoformat()}, period is {PERIOD_LABEL}'))
            monetary_fault = True

        due = parse_date(r.get('deliverable_due'))
        if r.get('deliverable_due') and due is None:
            row_issues.append(('R5', f"deliverable_due '{r.get('deliverable_due')}' cannot be read"))
        elif due and due < REPORT_AS_OF and tidy(r.get('deliverable_status')) != 'Complete':
            row_issues.append(('R7', f"due {due.isoformat()}, status '{tidy(r.get('deliverable_status'))}'"))

        cat = tidy(r.get('category'))
        if cat and cat not in VALID_CATEGORIES:
            row_issues.append(('R8', f"'{cat}' is not a recognised category"))

        for code, detail in row_issues:
            issues.append({
                'row': i, 'rule': code, 'rule_name': RULES[code], 'detail': detail,
                'project_code': tidy(r.get('project_code')),
                'invoice_ref': ref,
                'amount_eur': f'{disbursed:.2f}' if disbursed is not None else '',
                'excluded_from_totals': 'yes' if monetary_fault else 'no',
            })

        if not monetary_fault:
            clean.append({**r, '_allocated': allocated, '_disbursed': disbursed,
                          '_date': d_date, '_due': due,
                          '_project_name': tidy(r.get('project_name')),
                          '_budget_line': tidy(r.get('budget_line')),
                          '_category': cat})

    return issues, clean


# ---------------------------------------------------------------- indicators

def indicators(clean):
    """One row per project and budget line: allocated, disbursed, burn rate, variance."""
    agg = defaultdict(lambda: {'allocated': 0.0, 'disbursed': 0.0, 'lines': 0,
                               'overdue': 0, 'project_name': '', 'category': ''})
    for r in clean:
        # A row can be missing its project code (R1) and still be monetarily sound, so it
        # stays in the totals. Give it a visible label rather than an empty key, so the
        # reader sees a deliberate bucket instead of what looks like a broken row.
        k = (tidy(r.get('project_code')) or 'UNASSIGNED', r['_budget_line'])
        a = agg[k]
        a['allocated'] += r['_allocated']
        a['disbursed'] += r['_disbursed']
        a['lines'] += 1
        a['project_name'] = r['_project_name']
        a['category'] = r['_category']
        if r['_due'] and r['_due'] < REPORT_AS_OF and tidy(r.get('deliverable_status')) != 'Complete':
            a['overdue'] += 1

    out = []
    for (code, line), a in sorted(agg.items()):
        burn = a['disbursed'] / a['allocated'] if a['allocated'] else 0.0
        out.append({
            'project_code': code,
            'project_name': a['project_name'],
            'category': a['category'],
            'budget_line': line,
            'disbursements': a['lines'],
            'allocated_eur': round(a['allocated'], 2),
            'disbursed_eur': round(a['disbursed'], 2),
            'variance_eur': round(a['allocated'] - a['disbursed'], 2),
            'burn_rate': round(burn, 4),
            'overdue_deliverables': a['overdue'],
            # The flag a reviewer actually looks for first.
            # Thresholds a programme officer would actually act on: a line nearly spent
            # with months left, or barely touched with the period closing.
            'attention': ('Nearly fully spent' if burn >= 0.85
                          else 'Underspent' if burn <= 0.35 else ''),
        })
    return out


# ---------------------------------------------------------------- outputs

def write_csv(path, rows, fields):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_report(path, ind, issues, n_rows, n_clean):
    total_alloc = sum(r['allocated_eur'] for r in ind)
    total_disb = sum(r['disbursed_eur'] for r in ind)
    burn = total_disb / total_alloc if total_alloc else 0
    excluded = {i['row'] for i in issues if i['excluded_from_totals'] == 'yes'}
    by_rule = defaultdict(int)
    for i in issues:
        by_rule[i['rule']] += 1
    overdue = sum(r['overdue_deliverables'] for r in ind)
    # Show the largest lines by allocation, flagged where they need action. An
    # 'exceptions only' table that comes back empty tells the reader nothing;
    # the biggest lines are worth seeing whether or not they tripped a threshold.
    watch = sorted(ind, key=lambda r: -r['allocated_eur'])[:8]

    # The written summary. A dashboard without a sentence makes the reader do the work.
    summary = (
        f"Across {len(ind)} budget lines, EUR {total_disb:,.0f} of EUR {total_alloc:,.0f} "
        f"has been disbursed, a burn rate of {burn:.0%} with {(PERIOD_END - REPORT_AS_OF).days} days "
        f"of the period remaining. {len(excluded)} of {n_rows} rows were excluded from the totals "
        f"because of a monetary fault, and {len(issues)} issues were raised in all. "
        f"{overdue} deliverable{'s are' if overdue != 1 else ' is'} past due and not complete."
    )

    rows_html = '\n'.join(
        f"<tr><td>{r['project_code']}</td><td>{r['project_name']}</td><td>{r['budget_line']}</td>"
        f"<td class=n>{r['allocated_eur']:,.0f}</td><td class=n>{r['disbursed_eur']:,.0f}</td>"
        f"<td class=n>{r['burn_rate']:.0%}</td><td>{r['attention']}</td></tr>" for r in watch)
    issues_html = '\n'.join(
        f"<tr><td>{code}</td><td>{RULES[code]}</td><td class=n>{by_rule[code]}</td></tr>"
        for code in sorted(by_rule))

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Programme expenditure report</title>
<style>
  body {{ font: 13px/1.5 "IBM Plex Sans", -apple-system, Segoe UI, sans-serif; color:#14202e;
         max-width: 820px; margin: 32px auto; padding: 0 20px; }}
  h1 {{ font-size: 21px; margin: 0 0 2px; }}
  .stamp {{ color:#55657a; font-size:12px; margin-bottom:22px; }}
  h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing:.07em; color:#55657a;
        margin: 26px 0 8px; }}
  .summary {{ border-left:3px solid #1f3864; background:#eef1f6; padding:12px 15px; }}
  .stats {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
  .stat {{ border:1px solid #dde3ec; border-radius:8px; padding:10px 14px; min-width:120px; }}
  .stat .v {{ font-size:20px; font-weight:600; }}
  .stat .k {{ font-size:11px; color:#55657a; }}
  table {{ border-collapse: collapse; width:100%; font-size:12.5px; margin-top:6px; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.05em;
        color:#55657a; border-bottom:1px solid #dde3ec; padding:7px 8px; }}
  td {{ padding:6px 8px; border-bottom:1px solid #eef1f6; }}
  td.n, th.n {{ text-align:right; font-variant-numeric: tabular-nums; }}
  .foot {{ margin-top:26px; padding-top:10px; border-top:1px solid #dde3ec;
           font-size:11.5px; color:#8593a5; }}
  @media print {{ body {{ margin:0; }} }}
</style></head><body>
<h1>Programme expenditure report</h1>
<div class="stamp">Reporting period {PERIOD_LABEL} &middot; prepared {REPORT_AS_OF.strftime('%d %B %Y')} &middot; sample data</div>

<div class="summary">{summary}</div>

<div class="stats">
  <div class="stat"><div class="v">{burn:.0%}</div><div class="k">Burn rate</div></div>
  <div class="stat"><div class="v">{n_clean}/{n_rows}</div><div class="k">Rows in totals</div></div>
  <div class="stat"><div class="v">{len(issues)}</div><div class="k">Issues raised</div></div>
  <div class="stat"><div class="v">{overdue}</div><div class="k">Overdue deliverables</div></div>
</div>

<h2>Largest budget lines</h2>
<table><tr><th>Code</th><th>Project</th><th>Budget line</th><th class=n>Allocated</th>
<th class=n>Disbursed</th><th class=n>Burn</th><th>Flag</th></tr>
{rows_html}</table>

<h2>Issues by rule</h2>
<table><tr><th>Rule</th><th>What it checks</th><th class=n>Count</th></tr>
{issues_html}</table>

<div class="foot">Generated by grants_pipeline.py. Every figure traces to a row in
validation_report.csv; rows with a monetary fault are excluded from the totals and listed there.
Data is invented for demonstration.</div>
</body></html>"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)


# ---------------------------------------------------------------- main

def main(src=DEFAULT_IN):
    if not os.path.exists(src):
        sys.exit(f'No input file at {src}. Run make_sample_data.py first.')
    with open(src, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    issues, clean = validate(rows)
    ind = indicators(clean)
    os.makedirs(OUT_DIR, exist_ok=True)

    write_csv(os.path.join(OUT_DIR, 'validation_report.csv'), issues,
              ['row', 'rule', 'rule_name', 'detail', 'project_code', 'invoice_ref',
               'amount_eur', 'excluded_from_totals'])
    write_csv(os.path.join(OUT_DIR, 'indicators.csv'), ind,
              ['project_code', 'project_name', 'category', 'budget_line', 'disbursements',
               'allocated_eur', 'disbursed_eur', 'variance_eur', 'burn_rate',
               'overdue_deliverables', 'attention'])
    write_report(os.path.join(OUT_DIR, 'monthly_report.html'), ind, issues, len(rows), len(clean))

    print(f'{len(rows)} rows read, {len(clean)} clean, {len(issues)} issues across '
          f'{len({i["rule"] for i in issues})} rules')
    print('  output/validation_report.csv')
    print('  output/indicators.csv        <- Power BI reads this')
    print('  output/monthly_report.html   <- open in a browser, print to PDF')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN)
