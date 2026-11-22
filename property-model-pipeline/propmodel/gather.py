"""Address -> photo evidence pack, for local/internal project work.

Finds public listing pages for an address with the agent-reach CLI (web search + web read; no
browser, no logins), pulls the photo links and the basic facts off each page, downloads the photos
at the largest size the host serves, removes duplicates (across sites and sizes) with a perceptual
hash, and writes a manifest and a contact sheet.

Rules kept here on purpose:
* public pages only, through agent-reach; no private/undocumented APIs, no login, no bot-wall
  workarounds - a source that blocks is skipped and reported;
* people-search / owner-lookup sites are never read, and no owner or resident names are stored
  (only page URLs, titles and building facts);
* listing photos are copyrighted by their photographers/brokers: the pack is for internal
  measurement and modelling, kept outside the git repo (the job directory).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field

LISTING_SITES = ["zillow.com", "redfin.com", "realtor.com", "homes.com", "trulia.com", "coldwellbanker.com",
                 "century21.com", "remax.com", "compass.com", "movoto.com", "tophap.com", "har.com", "kw.com"]
# never read: people-search and owner-lookup sites (they publish names, phones, relatives)
BLOCKED = ["spokeo.", "whitepages.", "beenverified.", "fastpeoplesearch.", "truepeoplesearch.", "peoplefinders.",
           "intelius.", "radaris.", "thatsthem.", "mylife.", "clustrmaps.", "searchpeoplefree.", "countyoffice."]
STREET_TYPES = {"avenue": "ave", "ave": "ave", "street": "st", "st": "st", "road": "rd", "rd": "rd", "drive": "dr", "dr": "dr",
                "lane": "ln", "ln": "ln", "court": "ct", "ct": "ct", "circle": "cir", "cir": "cir", "boulevard": "blvd",
                "blvd": "blvd", "place": "pl", "pl": "pl", "way": "way", "terrace": "ter", "ter": "ter", "trail": "trl",
                "parkway": "pkwy", "pkwy": "pkwy", "highway": "hwy", "hwy": "hwy"}
DIRS = {"north": "n", "south": "s", "east": "e", "west": "w", "n": "n", "s": "s", "e": "e", "w": "w",
        "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw", "ne": "ne", "nw": "nw", "se": "se", "sw": "sw"}
IMG_RE = re.compile(r"https?://[^\s)\"'<>\]]+?\.(?:jpe?g|png|webp)(?:\?[^\s)\"'<>\]]*)?", re.I)
FACT_PATTERNS = {
    "beds": r"(\d+)\s*(?:bd|beds?|bedrooms?)\b",
    "baths": r"(\d+(?:\.\d+)?)\s*(?:ba|baths?|bathrooms?)\b",
    "sqft": r"([\d,]{3,6})\s*(?:sq\.?\s*ft|sqft|square feet)",
    "year_built": r"(?:built in|year built:?)\s*(\d{4})",
    "lot": r"([\d,.]+\s*(?:acres?|sq\.?\s*ft\.?\s*lot|sqft lot))",
    "roof": r"roof(?:ing)?(?: type| material)?:\s*([A-Za-z ,/-]{3,40})",
    "stories": r"(?:stories|levels):?\s*([\w -]{1,20})",
    "foundation": r"foundation(?: details)?:\s*([A-Za-z ,/-]{3,40})",
    "exterior": r"(?:exterior features|siding|construction materials):\s*([A-Za-z ,/-]{3,60})",
}


@dataclass
class Address:
    raw: str
    number: str
    street_tokens: list = field(default_factory=list)   # normalised: direction, name words, type
    city: str = ""
    state: str = ""
    zip: str = ""

    @property
    def key(self):
        return " ".join([self.number] + self.street_tokens)


def parse_address(raw: str) -> Address:
    s = raw.replace(".", " ").replace("#", " ")
    parts = [p.strip() for p in s.split(",")]
    first = parts[0].lower().split()
    if not first or not first[0].isdigit():
        raise ValueError(f"address must start with a house number: {raw!r}")
    toks = [DIRS.get(t, STREET_TYPES.get(t, t)) for t in first[1:]]
    a = Address(raw=raw, number=first[0], street_tokens=toks)
    rest = " ".join(parts[1:]).split()
    zipm = re.search(r"\b(\d{5})\b", " ".join(parts[1:]))
    a.zip = zipm.group(1) if zipm else ""
    st = [t for t in rest if re.fullmatch(r"[A-Za-z]{2}", t)]
    a.state = st[-1].upper() if st else ""
    if len(parts) > 1:
        a.city = re.sub(r"\b[A-Z]{2}\b|\d{5}", "", parts[1]).strip()
    return a


def slug_tokens(url: str):
    u = url.lower()
    u = re.sub(r"https?://[^/]+", "", u)
    return re.findall(r"[a-z0-9]+", u)


def matches(url: str, a: Address) -> bool:
    """The page is about exactly this address: house number followed by the street tokens in the URL."""
    toks = slug_tokens(url)
    want = [a.number] + [t for t in a.street_tokens if t not in STREET_TYPES.values()]
    norm = [DIRS.get(t, STREET_TYPES.get(t, t)) for t in toks]
    for i, t in enumerate(norm):
        if t != a.number:
            continue
        window = norm[i:i + len(a.street_tokens) + 3]
        if all(w in window for w in want[1:]):
            if a.city and a.city.split()[0].lower() not in norm:
                continue
            return True
    return False


def run_reach(args, timeout=120):
    exe = shutil.which("agent-reach")
    if not exe:
        raise RuntimeError("agent-reach CLI not found: install it from the agent-reach skill's bundled wheel")
    p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": {"code": "BAD_OUTPUT", "message": (p.stderr or p.stdout)[-400:]}}


def find_pages(a: Address, log=print, per_query=8):
    queries = [f"{a.raw}"] + [f"{a.number} {' '.join(a.street_tokens)} {a.city} {a.state} {site}" for site in
                              ("zillow", "redfin", "realtor.com", "homes.com", "trulia", "for sale photos", "sold")]
    seen, pages, skipped = set(), [], []
    for q in queries:
        d = run_reach(["web", "search", q, "--limit", str(per_query)])
        if not d.get("ok"):
            log(f"  search failed ({(d.get('error') or {}).get('code')}): {q}")
            continue
        for it in d.get("items", []):
            u = it.get("url") or ""
            if not u or u in seen:
                continue
            seen.add(u)
            if any(b in u for b in BLOCKED):
                skipped.append(u)
                continue
            if matches(u, a):
                pages.append({"url": u, "title": it.get("title") or "", "site": re.sub(r"^www\.", "", re.sub(r"https?://([^/]+).*", r"\1", u))})
        time.sleep(0.5)
    return pages, skipped


def gallery(text: str, gap=600) -> list:
    """The listing's own photos: the first tight run of image links in the page (the gallery). Later image
    runs belong to 'nearby homes' / 'similar homes' strips about other houses, and are dropped."""
    hits = [(m.start(), m.group(0)) for m in IMG_RE.finditer(text)
            if not re.search(r"logo|avatar|headshot|agent|icon|sprite|maps?\.|staticmap|badge|brand|favicon", m.group(0), re.I)]
    if not hits:
        return []
    run = [hits[0]]
    for pos, u in hits[1:]:
        if pos - run[-1][0] > gap:
            break
        run.append((pos, u))
    # one photo can be listed at several sizes: keep one link per photo id (path without the size suffix)
    seen, out = set(), []
    for _, u in run:
        key = re.sub(r"[-_](?:cc_ft|uncropped_scaled_within|p|w\d+_h\d+|od)[\w-]*\.(jpe?g|png|webp).*$", "", u)
        if key not in seen:
            seen.add(key); out.append(u)
    return out


def upscale(url: str) -> list:
    """Candidate URLs for the same photo, largest first."""
    out = []
    if "photos.zillowstatic.com" in url:
        base = re.sub(r"-(?:cc_ft|uncropped_scaled_within|p)_[\w]+\.(jpe?g|webp|png)$", "", url)
        if base != url:
            out += [f"{base}-uncropped_scaled_within_1536_1152.jpg", f"{base}-cc_ft_1536.jpg", f"{base}-cc_ft_960.jpg"]
    if "rdcpix.com" in url:      # realtor.com
        out.append(re.sub(r"(-[a-z]\d*)?(?:s|m|l)?\.jpg$", "-w1024_h768.jpg", url))
    if "ssl.cdn-redfin.com" in url:
        out.append(re.sub(r"/(?:genMid|genBcs|islphoto)\.", "/bigphoto/", url))
    out.append(url)
    return list(dict.fromkeys(out))


def ahash(img, n=12):
    g = img.convert("L").resize((n, n))
    px = list(g.getdata()); m = sum(px) / len(px)
    return int("".join("1" if p > m else "0" for p in px), 2)


def hamming(a, b):
    return bin(a ^ b).count("1")


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (property-model-pipeline)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def gather(address: str, out_dir: str, log=print, max_photos=120, min_side=480):
    from PIL import Image
    a = parse_address(address)
    os.makedirs(out_dir, exist_ok=True)
    pdir = os.path.join(out_dir, "photos", "listing")
    os.makedirs(pdir, exist_ok=True)
    log(f"searching listing pages for {a.key} ({a.city} {a.state} {a.zip})")
    pages, skipped = find_pages(a, log=log)
    log(f"  {len(pages)} matching page(s); {len(skipped)} people-search page(s) skipped unread")
    manifest = {"address": address, "normalized": a.key, "captured": time.strftime("%Y-%m-%d"), "pages": [], "photos": [],
                "skipped_people_search": len(skipped), "notes": [
                    "Listing photos are copyrighted (photographer / broker); internal measurement and modelling use only.",
                    "No owner or resident names are stored; people-search sites are never read."]}
    hashes = []
    for pg in pages:
        d = run_reach(["web", "read", pg["url"]], timeout=180)
        rec = {**pg, "ok": bool(d.get("ok")), "facts": {}, "images_found": 0}
        if not d.get("ok"):
            rec["error"] = (d.get("error") or {}).get("code")
            manifest["pages"].append(rec); log(f"  read failed {pg['site']}: {rec['error']}")
            continue
        text = "\n".join((it.get("text") or "") for it in d.get("items", []))
        # does the page really describe this house (not a neighbour on a 'nearby homes' strip)?
        if a.number not in text[:4000]:
            rec["note"] = "address not in the page header; skipped"; manifest["pages"].append(rec); continue
        for k, pat in FACT_PATTERNS.items():
            m = re.search(pat, text, re.I)
            if m:
                rec["facts"][k] = m.group(1).strip()
        imgs = gallery(text)
        m_all = re.search(r"see all\s+(\d+)\s+photos", text, re.I)
        if m_all:
            rec["photos_listed"] = int(m_all.group(1))
        rec["images_found"] = len(imgs)
        manifest["pages"].append(rec)
        sdir = os.path.join(pdir, re.sub(r"[^a-z0-9]+", "_", pg["site"]))
        os.makedirs(sdir, exist_ok=True)
        for u in imgs:
            if len(manifest["photos"]) >= max_photos:
                break
            got = None
            for cand in upscale(u):
                try:
                    data, ctype = fetch(cand)
                    if "image" not in ctype:
                        continue
                    im = Image.open(io.BytesIO(data)); im.load()
                    got = (cand, data, im); break
                except Exception:
                    continue
            if not got:
                continue
            cand, data, im = got
            if min(im.size) < min_side:
                continue
            h = ahash(im)
            dup = next((i for i, hh in enumerate(hashes) if hamming(h, hh) <= 6), None)
            if dup is not None:
                prev = manifest["photos"][dup]
                if im.size[0] * im.size[1] > prev["size"][0] * prev["size"][1]:   # keep the larger copy
                    with open(prev["file"], "wb") as f: f.write(data)
                    prev.update({"size": list(im.size), "source": cand})
                continue
            fn = os.path.join(sdir, f"{len(manifest['photos']) + 1:03d}.jpg")
            if im.format == "JPEG":
                with open(fn, "wb") as f: f.write(data)
            else:
                im.convert("RGB").save(fn, quality=92)
            hashes.append(h)
            manifest["photos"].append({"file": fn, "source": cand, "page": pg["url"], "site": pg["site"], "size": list(im.size),
                                       "sha1": hashlib.sha1(data).hexdigest()})
        log(f"  {pg['site']}: {rec['images_found']} image links, {len(manifest['photos'])} unique photos so far")
    with open(os.path.join(out_dir, "photos_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    if manifest["photos"]:
        contact_sheet([p["file"] for p in manifest["photos"]], os.path.join(out_dir, "photos_contact.jpg"))
    log(f"done: {len(manifest['photos'])} photos from {sum(1 for p in manifest['pages'] if p.get('images_found'))} page(s) -> {out_dir}")
    return manifest


def contact_sheet(files, out, cols=6, w=300):
    from PIL import Image, ImageDraw
    ims = []
    for f in files:
        try:
            im = Image.open(f).convert("RGB"); im.thumbnail((w, w)); ims.append((os.path.basename(os.path.dirname(f)) + "/" + os.path.basename(f), im))
        except Exception:
            pass
    if not ims:
        return
    h = max(im.size[1] for _, im in ims) + 18
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), "white"); d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(ims):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y)); d.text((x + 4, y + h - 16), name, fill="black")
    sheet.save(out, quality=85)
