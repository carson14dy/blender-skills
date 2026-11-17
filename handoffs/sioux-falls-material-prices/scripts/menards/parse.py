"""Parse Menards category page text (as returned by the web reader) into product rows."""
import csv, json, re, sys

PRICE_RE = re.compile(r'^(SALE )?PRICE\s*\$([\d,]+\.\d\d)(?:\s*11% REBATE\*\s*\$([\d,]+\.\d\d))?')
VAR_RE = re.compile(r'^\s*(\d+) (Variations|More Options) Available')
VAR_DOLLAR = re.compile(r'VALUE AFTER REBATE\*\s*(STARTING AT\s*)?\$\s*(\d[\d,]*)\s+(\d\d)\s*(\S.*)?$')
SKU_RE = re.compile(r'\s*Sku # (\d+)\s*$')
NOISE = ('# ', 'URL:', 'Roofing at Menards', 'Roof Flashing at Menards', 'DELIVERY',
         'Increments of', 'Free Shipping to Store', 'VALUE AFTER REBATE', 'PICK UP')


def parse(text, category, source_url):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows, pending, attrs = [], None, set()
    i = 0
    while i < len(lines):
        l = lines[i]
        # split-line price format: "SALE PRICE $48.30" / "11% REBATE* $5.31"
        m = PRICE_RE.match(l)
        if m:
            rebate = m.group(3)
            if not rebate and i + 1 < len(lines) and lines[i + 1].startswith('11% REBATE'):
                rebate = re.search(r'\$([\d,]+\.\d\d)', lines[i + 1]).group(1); i += 1
            var, starting, unit = None, False, ''
            if i + 1 < len(lines) and lines[i + 1].startswith('VALUE AFTER REBATE'):
                vm = VAR_DOLLAR.search(lines[i + 1])
                if vm:
                    var = f"{vm.group(2).replace(',', '')}.{vm.group(3)}"
                    starting = bool(vm.group(1)); unit = (vm.group(4) or '').strip()
                i += 1
            name, sku = (pending or ('', ''))
            rows.append(dict(category=category, product=name or '(name not captured)', menards_sku=sku,
                             price_type='sale' if m.group(1) else 'regular',
                             price=float(m.group(2).replace(',', '')),
                             rebate_11pct=float(rebate.replace(',', '')) if rebate else None,
                             value_after_rebate=float(var) if var else None,
                             starting_at='yes' if starting else '', unit=unit,
                             notes='; '.join(sorted(attrs)), source_url=source_url))
            pending, attrs = None, set()
        elif VAR_RE.match(l) or l in ('Free Shipping to Store', 'DELIVERY', 'PICK UP', 'SHIP TO HOME') or l.startswith('Increments of'):
            attrs.add(l.strip())
        elif l.startswith(NOISE) or l.startswith('11% REBATE') or re.fullmatch(r'[\d$ ]+', l):
            pass
        else:
            if pending:  # previous product had no captured price
                rows.append(dict(category=category, product=pending[0], menards_sku=pending[1], price_type='',
                                 price=None, rebate_11pct=None, value_after_rebate=None, starting_at='',
                                 unit='', notes='price not captured', source_url=source_url))
            sm = SKU_RE.search(l)
            pending = (SKU_RE.sub('', l).strip(), sm.group(1) if sm else '')
        i += 1
    if pending:
        rows.append(dict(category=category, product=pending[0], menards_sku=pending[1], price_type='', price=None,
                         rebate_11pct=None, value_after_rebate=None, starting_at='', unit='',
                         notes='price not captured', source_url=source_url))
    # fill missing value-after-rebate where price and rebate are known
    for r in rows:
        if r['value_after_rebate'] is None and r['price'] is not None and r['rebate_11pct'] is not None:
            r['value_after_rebate'] = round(r['price'] - r['rebate_11pct'], 2)
            r['notes'] = (r['notes'] + '; ' if r['notes'] else '') + 'value after rebate computed'
    return rows


if __name__ == '__main__':
    out_csv, out_json, *pairs = sys.argv[1:]
    allrows = []
    for p in pairs:
        path, category = p.split('::')
        d = json.load(open(path))
        for it in d.get('items', []):
            allrows += parse(it.get('text', ''), category, it.get('url', ''))
    fields = list(allrows[0].keys())
    with open(out_csv, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(allrows)
    json.dump(allrows, open(out_json, 'w'), indent=1)
    print(len(allrows), 'rows')
