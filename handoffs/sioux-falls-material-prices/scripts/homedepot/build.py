"""Turn captured Home Depot listing data into a handoff workbook + CSV."""
import csv, glob, json, os, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

data_dir, out_dir = sys.argv[1:3]
HD = 'https://www.homedepot.com'


def g(d, *ks, default=None):
    for k in ks:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return d if d is not None else default


def store_info(p):
    """Return (pickup in stock?, qty at Sioux Falls, delivery available?)."""
    qty, instock, delivery = None, None, False
    for opt in g(p, 'fulfillment', 'fulfillmentOptions', default=[]) or []:
        for svc in opt.get('services') or []:
            if opt.get('type') == 'delivery' and opt.get('fulfillable'):
                delivery = True
            for loc in svc.get('locations') or []:
                if loc.get('locationId') == '4301' and svc.get('type') == 'bopis':
                    inv = loc.get('inventory') or {}
                    qty, instock = inv.get('quantity'), inv.get('isInStock')
    return instock, qty, delivery


rows, seen, coverage = [], {}, []
log = [x for f in sorted(glob.glob(os.path.join(data_dir, '_log*.json'))) for x in json.load(open(f))]
PRIORITY = ['Soffit', 'Fascia', 'Skylights', 'Roof_Shingles', 'Roof_Underlayments', 'Roof_Flashing', 'Roof_Panels',
            'Roll_Roofing', 'Gutter_Systems', 'Commercial_Roofing', 'Roof_Vents', 'Roofing_Tools']


def prio(f):
    b = os.path.basename(f)
    return next((i for i, k in enumerate(PRIORITY) if b.startswith(k)), len(PRIORITY)), b


for f in sorted(glob.glob(os.path.join(data_dir, '*.json')), key=prio):
    if os.path.basename(f).startswith('_'):
        continue
    d = json.load(open(f))
    for p in d['items']:
        iid = p.get('itemId') or g(p, 'identifiers', 'itemId')
        if iid in seen:
            if d['name'].split(':')[0] != seen[iid]['category']: seen[iid]['also_listed_in'].add(d['name'].split(':')[0])
            continue
        pr = p.get('pricing') or {}
        promo = pr.get('promotion') or {}
        unit = g(pr, 'alternate', 'unit') or {}
        instock, qty, delivery = store_info(p)
        hier = g(p, 'info', 'categoryHierarchy', default=[]) or []
        r = dict(
            category=d['name'].split(':')[0],
            subcategory=' > '.join(hier[2:]) if len(hier) > 2 else '',
            brand=g(p, 'identifiers', 'brandName', default=''),
            product=g(p, 'identifiers', 'productLabel', default=''),
            model=g(p, 'identifiers', 'modelNumber', default=''),
            store_sku=g(p, 'identifiers', 'storeSkuNumber', default=''),
            internet_id=iid,
            price=pr.get('value'),
            was_price=pr.get('original') if pr.get('original') and pr.get('value') and pr['original'] > pr['value'] else None,
            pct_off=promo.get('percentageOff') or None,
            price_uom=pr.get('unitOfMeasure') or '',
            unit_price=unit.get('value'),
            unit_uom=unit.get('caseUnitOfMeasure') or '',
            units_per_case=unit.get('unitsPerCase'),
            price_hidden_map='yes' if g(p, 'info', 'hidePrice') or pr.get('mapDetail') else '',
            sioux_falls_in_stock={True: 'yes', False: 'no'}.get(instock, ''),
            sioux_falls_qty=qty,
            delivery_available='yes' if delivery else '',
            rating=round(float(g(p, 'reviews', 'ratingsReviews', 'averageRating', default=0) or 0), 2) or None,
            reviews=int(g(p, 'reviews', 'ratingsReviews', 'totalReviews', default=0) or 0) or None,
            url=HD + (g(p, 'identifiers', 'canonicalUrl', default='') or ''),
            also_listed_in=set(),
        )
        imgs = g(p, 'media', 'images', default=[]) or []
        prim = next((i for i in imgs if i.get('subType') == 'PRIMARY'), imgs[0] if imgs else None)
        r['image_url'] = prim['url'].replace('<SIZE>', '1000') if prim else ''
        sw = g(p, 'info', 'swatches', default=[]) or []
        sel = next((s for s in sw if s.get('isSelected')), None)
        r['color'] = sel.get('label', '') if sel else ''
        r['color_options'] = len(sw) or None
        at = p.get('availabilityType') or {}
        r['availability'] = (at.get('type') or '') + (' (no online price; ask store)' if r['price'] is None else '')
        r['_swatches'] = [dict(label=s.get('label'), item_id=s.get('itemId'), swatch_image=s.get('swatchImgUrl'),
                               url=HD + (s.get('url') or '')) for s in sw]
        seen[iid] = r
        rows.append(r)
for r in rows:
    r['also_listed_in'] = ', '.join(sorted(r['also_listed_in']))

cols = [('category', 'Category', 30), ('subcategory', 'Subcategory', 28), ('brand', 'Brand', 16),
        ('product', 'Product', 70), ('model', 'Model #', 14), ('store_sku', 'Store SKU', 10),
        ('internet_id', 'Internet #', 11), ('price', 'Price ($)', 10), ('was_price', 'Was ($)', 9),
        ('pct_off', '% off', 7), ('price_uom', 'Price per', 10), ('unit_price', 'Unit price ($)', 11),
        ('unit_uom', 'Unit', 10), ('units_per_case', 'Units per pkg', 10),
        ('sioux_falls_in_stock', 'In stock Sioux Falls', 10), ('sioux_falls_qty', 'Qty at store', 9),
        ('delivery_available', 'Delivery', 9), ('price_hidden_map', 'Price hidden (see cart)', 11),
        ('rating', 'Rating', 7), ('reviews', 'Reviews', 8), ('also_listed_in', 'Also listed in', 24),
        ('availability', 'Availability', 22),
        ('color', 'Color (this listing)', 18), ('color_options', 'Color options', 9),
        ('image_url', 'Product image', 40), ('url', 'Link', 60)]

hdr = PatternFill('solid', fgColor='1F3A5F')
wb = Workbook()
ws = wb.active; ws.title = 'Products'
ws.append([c[1] for c in cols])
for r in sorted(rows, key=lambda r: (r['category'], r['subcategory'], r['brand'], r['product'])):
    ws.append([r[c[0]] for c in cols])
for c in ws[1]:
    c.font = Font(bold=True, color='FFFFFF'); c.fill = hdr
    c.alignment = Alignment(wrap_text=True, vertical='top')
for i, c in enumerate(cols, 1):
    ws.column_dimensions[get_column_letter(i)].width = c[2]
money = {cols.index(c) for c in cols if c[0] in ('price', 'was_price', 'unit_price')}
for row in ws.iter_rows(min_row=2):
    for i in money:
        row[i].number_format = '$#,##0.00'
    link = row[len(cols) - 1]
    if link.value:
        link.hyperlink = link.value; link.font = Font(color='0563C1', underline='single')
ws.freeze_panes = 'E2'; ws.auto_filter.ref = ws.dimensions

s = wb.create_sheet('Summary')
s.append(['Category', 'Products listed (store)', 'Unique captured', 'In stock at Sioux Falls', 'Min price ($)',
          'Median price ($)', 'Max price ($)'])
import statistics
agg = {}
for L in log:
    if 'path' not in L:
        continue
    nm = L['name'].split(':')[0]
    A = agg.setdefault(nm, dict(name=nm, total=0))
    if ':' not in L['name']:
        A['total'] = max(A['total'], L.get('total') or 0)
for L in agg.values():
    cr = [r for r in rows if r['category'] == L['name']]
    L['captured'] = len(cr)
    pr = sorted(r['price'] for r in cr if r['price'])
    s.append([L['name'], L.get('total'), L.get('captured'), sum(1 for r in cr if r['sioux_falls_in_stock'] == 'yes'),
              pr[0] if pr else None, statistics.median(pr) if pr else None, pr[-1] if pr else None])
s.append(['Unique products (de-duplicated)', None, len(rows)])
for c in s[1]:
    c.font = Font(bold=True, color='FFFFFF'); c.fill = hdr; c.alignment = Alignment(wrap_text=True)
for i, w in enumerate([44, 14, 11, 14, 12, 14, 12], 1):
    s.column_dimensions[get_column_letter(i)].width = w

e = wb.create_sheet('Capture log')
e.append(['Category', 'Start offset', 'Status / error'])
for L in log:
    if 'error' in L:
        e.append([L['name'], L.get('start'), f"{L.get('status', '')} {L['error']}"])
if e.max_row == 1:
    e.append(['(none)', '', 'All pages captured without errors'])
e.column_dimensions['A'].width = 44; e.column_dimensions['C'].width = 80

xlsx = os.path.join(out_dir, 'homedepot_sioux_falls_roofing.xlsx')
wb.save(xlsx)
with open(os.path.join(out_dir, 'homedepot_sioux_falls_roofing.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow([c[1] for c in cols])
    for row in ws.iter_rows(min_row=2, values_only=True):
        w.writerow(row)
print('rows', len(rows))
for row in s.iter_rows(values_only=True):
    print(row)

# 3D-studio friendly materials file: one record per product, with color variants and images
mats = []
for r in sorted(rows, key=lambda r: (r['category'], r['subcategory'], r['brand'], r['product'])):
    mats.append(dict(
        id=r['internet_id'], name=r['product'], brand=r['brand'], category=r['category'],
        subcategory=r['subcategory'], color=r['color'], price=r['price'], price_per=r['price_uom'],
        unit_price=r['unit_price'], unit=r['unit_uom'], units_per_package=r['units_per_case'], availability=r['availability'],
        in_stock_sioux_falls=r['sioux_falls_in_stock'] == 'yes', qty_sioux_falls=r['sioux_falls_qty'],
        image=r['image_url'], url=r['url'], color_variants=r['_swatches']))
json.dump(dict(store='The Home Depot #4301, 2523 S Louise Ave, Sioux Falls, SD 57106',
               note='Prices/inventory for this store as shown online; color_variants other than the listed color '
                    'may have different prices (check their url / item_id).',
               products=mats), open(os.path.join(out_dir, 'materials.json'), 'w'), indent=1)
print('materials.json', len(mats))
