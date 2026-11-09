# Grants and expenditure reporting pipeline

Takes a programme spend file, checks it against eight named validation rules, computes
the indicators a programme office reports upward, and produces a one-page report.

This is a reporting process I used to run by hand — monitoring county government
expenditure on public infrastructure projects and preparing the monthly report for
leadership — rebuilt so that it runs in a second and gives the same answer every time.

**Standard library only.** No dependencies, nothing to install, runs on any machine with
Python 3.

---

## Run it

```bash
python3 make_sample_data.py     # writes data/programme_spend.csv
python3 grants_pipeline.py      # writes the three outputs
```

To use a different file: `python3 grants_pipeline.py path/to/your.csv`

## Outputs

| File | What it is |
|---|---|
| `output/monthly_report.html` | One-page summary with a written lede. Open in a browser, print to PDF |
| `output/indicators.csv` | One row per project and budget line — the feed for Power BI or Excel |
| `output/validation_report.csv` | Every issue found, with the row number and the rule that caught it |

## The validation rules

| Rule | Checks | Excludes the row from totals? |
|---|---|---|
| R1 | Required field is empty | No |
| R2 | Duplicate invoice reference — the same invoice paid twice | No |
| R3 | Disbursed exceeds allocated | **Yes** |
| R4 | Disbursement dated outside the reporting period | **Yes** |
| R5 | A date or amount cannot be read | **Yes** |
| R6 | Amount is zero or negative | **Yes** |
| R7 | Deliverable overdue and not marked complete | No |
| R8 | Category outside the controlled list | No |

**The last column is the design decision the rest of the project hangs on.** A row with a
monetary fault is held out of the totals, because including it would misstate the report —
and every excluded row appears in `validation_report.csv` with the reason. A row with a
missing supplier name still counts; it is flagged, not dropped.

Being able to say *which* rows were excluded and why is what makes a total defensible when
somebody asks. That distinction is a reporting judgement rather than a technical one, and
it is the part of this that came from doing the job.

On the sample file: **120 rows in, 113 counted, 27 issues raised across all eight rules.**

## Parsing, because real files are not clean

`money()` and `parse_date()` accept what people actually type and what Excel actually
exports — `85,000.00`, ` 32 400.00 `, `31/04/2026`, `tbc` — and return `None` rather than
guessing when a value cannot be read. A silent zero is how a wrong total gets published.

## The sample data is invented

`make_sample_data.py` generates it, seeded so it is identical on every run. It contains no
real programme or organisational data. The generator deliberately plants one fault of each
kind — a double-paid invoice, an over-disbursement, an unparseable date, an amount with a
thousands separator — so the validation has something genuine to catch.

## Possible extensions

- Point Power BI at `output/indicators.csv` for the burn-rate visual
- Flag a supplier appearing across several projects above a threshold value
- Run two periods and report the movement between them

---

Built in Python with AI assistance; the rules, the data model and the exclusion logic are
mine, from six years of programme coordination and public expenditure monitoring.
