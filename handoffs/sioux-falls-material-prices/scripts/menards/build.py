"""Build the handoff workbook from products.json."""
import json, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

src, out_xlsx, out_csv = sys.argv[1:4]
rows = json.load(open(src))

GROUPS = [('Shingles', ('shingle',)), ('Metal roofing panels', ('steel panel', 'pro-rib', 'pro-snap')),
          ('Underlayment & ice/water', ('underlayment', 'felt', 'leak barrier', 'ice & water')),
          ('Pipe/vent flashing', ('vent pipe flashing', 'pipe flashing')),
          ('Step/kick-out/chimney flashing', ('step flashing', 'kick out', 'chimney', 'reglet')),
          ('Valley', ('roll valley',)), ('Trim coil', ('trim coil', 'steel coil')),
          ('Drip edge & roof edge trim', ('drip edge', 'roof edge', 'gutter apron', 'rake trim', 'gable trim')),
          ('Polycarbonate panels', ('polycarbonate',))]


def group(name):
    n = name.lower()
    for g, keys in GROUPS:
        if any(k in n for k in keys):
            return g
    return 'Other / unknown'


seen = {}
for r in rows:
    r['product_group'] = group(r['product'])
    key = r['menards_sku'] or r['product']
    r['duplicate_of_row'] = seen.get(key, '') if key and r['product'] != '(name not captured)' else ''
    seen.setdefault(key, rows.index(r) + 2)

cols = ['product_group', 'product', 'menards_sku', 'price_type', 'price', 'rebate_11pct', 'value_after_rebate',
        'starting_at', 'unit', 'notes', 'category', 'duplicate_of_row', 'source_url']
heads = ['Product group', 'Product', 'Menards SKU', 'Price type', 'Price ($)', '11% rebate ($)',
         'Value after rebate ($)', 'Starting at?', 'Unit', 'Notes', 'Page captured from', 'Duplicate of row',
         'Source URL']

wb = Workbook()
ws = wb.active; ws.title = 'Products'
ws.append(heads)
for r in sorted(rows, key=lambda r: (r['product_group'], r['product'])):
    ws.append([r[c] for c in cols])
hdr = PatternFill('solid', fgColor='1F3A5F')
for c in ws[1]:
    c.font = Font(bold=True, color='FFFFFF'); c.fill = hdr; c.alignment = Alignment(wrap_text=True, vertical='top')
widths = [26, 60, 12, 10, 10, 12, 14, 10, 12, 40, 24, 10, 60]
for i, w in enumerate(widths, 1):
    ws.column_dimensions[get_column_letter(i)].width = w
for row in ws.iter_rows(min_row=2):
    for c in row[4:7]:
        c.number_format = '$#,##0.00'
ws.freeze_panes = 'C2'; ws.auto_filter.ref = ws.dimensions
# duplicate_of_row refers to the unsorted CSV; recompute on sorted sheet
first = {}
for i, row in enumerate(ws.iter_rows(min_row=2), start=2):
    key = row[2].value or row[1].value
    if key == '(name not captured)':
        row[11].value = ''; continue
    row[11].value = first.get(key, '')
    first.setdefault(key, i)

s = wb.create_sheet('Summary')
s.append(['Product group', 'Items', 'Items with price', 'Min price ($)', 'Max price ($)'])
for g in sorted({r['product_group'] for r in rows}):
    gp = [r for r in rows if r['product_group'] == g]
    pr = [r['price'] for r in gp if r['price'] is not None]
    s.append([g, len(gp), len(pr), min(pr) if pr else None, max(pr) if pr else None])
for c in s[1]:
    c.font = Font(bold=True, color='FFFFFF'); c.fill = hdr
for i, w in enumerate([30, 8, 16, 14, 14], 1):
    s.column_dimensions[get_column_letter(i)].width = w

cov = wb.create_sheet('Coverage')
cov.append(['Roofing subcategory', 'URL', 'Captured?', 'Why'])
for line in open(sys.argv[4]):
    name, url, status, why = line.rstrip('\n').split('\t')
    cov.append([name, url, status, why])
for c in cov[1]:
    c.font = Font(bold=True, color='FFFFFF'); c.fill = hdr
for i, w in enumerate([34, 90, 12, 70], 1):
    cov.column_dimensions[get_column_letter(i)].width = w
wb.save(out_xlsx)

import csv
with open(out_csv, 'w', newline='') as f:
    w = csv.writer(f); w.writerow(heads)
    for row in ws.iter_rows(min_row=2, values_only=True):
        w.writerow(row)
print('ok', len(rows))
