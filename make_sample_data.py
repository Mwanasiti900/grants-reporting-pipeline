"""Generate a sample programme-expenditure file for the grants reporting pipeline.

THE DATA IS INVENTED. Nothing here comes from the Office of the Senator of Kwale County
or from any real programme. The structure mirrors the kind of file a programme office
actually keeps - one row per disbursement against a budget line - and the generator
deliberately introduces the errors that turn up in real files, so the validation step in
grants_pipeline.py has something to catch.

Usage:  python3 make_sample_data.py
Writes: data/programme_spend.csv
"""
import csv, random, os
from datetime import date, timedelta

random.seed(7)  # same file every run, so results are reproducible when demonstrating

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data', 'programme_spend.csv')

PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 12, 31)
REPORT_AS_OF = date(2026, 11, 9)   # must match grants_pipeline.py

PROJECTS = [
    ('KWP-01', 'Rural road rehabilitation', 'Infrastructure'),
    ('KWP-02', 'Market construction',       'Infrastructure'),
    ('KWP-03', 'Social hall upgrade',       'Infrastructure'),
    ('KWP-04', 'Water point maintenance',   'Services'),
    ('KWP-05', 'Community training',        'Capacity building'),
    ('KWP-06', 'Monitoring and reporting',  'Programme support'),
]

BUDGET_LINES = ['Works', 'Goods', 'Consultancy', 'Travel', 'Training', 'Administration']
SUPPLIERS = ['Bahari Contractors', 'Mwenge Supplies', 'Tatu Consulting', 'Pwani Logistics',
             'Jenga Works', 'Upeo Services']
DELIVERABLE_STATUS = ['Complete', 'In progress', 'Not started']


def rand_date(start, end):
    return start + timedelta(days=random.randint(0, (end - start).days))


def build_rows(n=120):
    rows = []
    for i in range(n):
        code, name, category = random.choice(PROJECTS)
        allocated = random.choice([25000, 40000, 60000, 85000, 120000, 150000])
        disbursed = round(allocated * random.uniform(0.15, 0.95), 2)
        d_date = rand_date(PERIOD_START, PERIOD_END)
        due = rand_date(PERIOD_START, PERIOD_END)
        rows.append({
            'project_code': code,
            'project_name': name,
            'category': category,
            'budget_line': random.choice(BUDGET_LINES),
            'allocated_eur': f'{allocated:.2f}',
            'disbursed_eur': f'{disbursed:.2f}',
            'disbursement_date': d_date.isoformat(),
            'supplier': random.choice(SUPPLIERS),
            'invoice_ref': f'INV-2026-{1000 + i}',
            'deliverable': f'{name} - milestone {random.randint(1, 4)}',
            'deliverable_due': due.isoformat(),
            # A real file is mostly in order: deliverables already past their date are
            # usually marked complete. Leaving the status random made half the file
            # look overdue, which buries the handful that genuinely are.
            'deliverable_status': ('Complete' if due < REPORT_AS_OF and random.random() < 0.92
                                   else random.choice(DELIVERABLE_STATUS)),
        })
    return rows


def dirty(rows):
    """Introduce the faults a real file carries, so the validation has work to do.

    Each fault below maps to one rule in grants_pipeline.py. Keeping them explicit
    means the demonstration can show the rule that caught each one.
    """
    # R1 missing required fields
    rows[3]['supplier'] = ''
    rows[17]['invoice_ref'] = ''
    rows[41]['project_code'] = ''

    # R2 duplicate invoice reference - the same invoice paid twice
    rows[25]['invoice_ref'] = rows[24]['invoice_ref']
    rows[78]['invoice_ref'] = rows[11]['invoice_ref']

    # R3 disbursed exceeds allocated
    rows[8]['disbursed_eur'] = f"{float(rows[8]['allocated_eur']) * 1.18:.2f}"
    rows[52]['disbursed_eur'] = f"{float(rows[52]['allocated_eur']) * 1.05:.2f}"

    # R4 disbursement outside the reporting period
    rows[30]['disbursement_date'] = '2025-11-04'
    rows[64]['disbursement_date'] = '2027-02-15'

    # R5 unparseable date
    rows[12]['disbursement_date'] = '31/04/2026'
    rows[71]['deliverable_due'] = 'tbc'

    # R6 zero or negative amount
    rows[20]['disbursed_eur'] = '0.00'
    rows[55]['disbursed_eur'] = '-4200.00'

    # R7 overdue deliverable still open
    rows[5]['deliverable_due'] = '2026-03-31'
    rows[5]['deliverable_status'] = 'In progress'
    rows[33]['deliverable_due'] = '2026-01-15'
    rows[33]['deliverable_status'] = 'Not started'

    # R8 category outside the controlled list
    rows[47]['category'] = 'Misc'

    # Formatting noise: thousands separators and stray spaces, as exported from Excel
    rows[2]['allocated_eur'] = '85,000.00'
    rows[60]['disbursed_eur'] = ' 32 400.00 '
    rows[9]['project_name'] = '  Market construction '
    return rows


if __name__ == '__main__':
    rows = dirty(build_rows())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'wrote {len(rows)} rows to {OUT}')
