# 019 · Steel panel profiles

| | |
|---|---|
| Track | T2, project `lab/projects/sioux-falls-studio/` |
| Session | cloud |
| Date | 2026-11-16 |
| Status | texture part done, geometry later |

## Question

Can the store's steel panels be drawn at their measured profile in the web studio, so a homeowner can choose between Pro-Rib, Pro-Snap and corrugated on the roof? This step covers textures only. Real rib geometry, the metal ridge cap and rake trim are later (plan section 2), together with step 020 and the `roof_qa.py` gate.

## Method

- **Textures** (`roof-visualizer/viewer/js/textures.js`, appended):
  - **`ribbedPanel`** is an exposed-fastener rib panel. Its tile is one panel cover wide (36 in.).
    - Trapezoid major ribs sit on every multiple of the rib spacing (9 in.): 0.75 in. high, 0.75 in. top, 1.75 in. base.
    - Two low stiffening ribs lie between them (0.12 of the height, 0.6 in. wide).
    - Painted screw heads sit beside each rib at 24 in. on centre.
  - **`corrugatedPanel`** is a sine profile, 2.67 in. pitch and 0.5 in. deep. Its tile is 8 pitches.
  - The height map becomes the normal map, with a strength of pixels per inch / 8. A rib side therefore tilts the light by its real slope.
- **Recipes** (`supplier-products.js`):
  - Menards Pro-Rib becomes `ribbedPanel` with its catalog rib spacing and height (9 in., 0.75 in.).
  - Pro-Snap becomes the existing `standingSeam` at 16 in.
  - Home Depot corrugated becomes `corrugatedPanel`.
  - Home Depot panels with no stated profile become `ribbedPanel`, with the note "profile assumed: the store does not state it".
- **Material:** metalness and roughness come from the catalog `pbr`.
  - Menards painted steel: metallic 0, roughness 0.4, from its material table.
  - Home Depot by rule: painted 0.3 / 0.45, galvanized 0.9 / 0.35.
- **Measured in the page** (`lab/tools/supplier-shots.mjs --checks`):
  - `1 / material.map.repeat.x` of the covering mesh, which is the real width of one texture tile on the roof;
  - the generator's ribs per tile.

## Result

| Product | Tile on the roof | Profile | Spec |
|---|---|---|---|
| Menards Pro-Rib Ash Gray (`mn-1444448546780`) | 0.9144 m = 36.00 in. | 4 ribs per tile = **9.00 in. on centre** | 36 in. cover, 9 in. ribs |
| Home Depot corrugated (`hd-338539708`) | 21.36 in. | 8 × 2.67 in. pitch | common profile (not store data; the card says so) |
| Menards Pro-Snap Midnight Black (`mn-4283774896157214`) | 32.00 in. | 2 panels, a seam every 16.00 in. | 16 in. coverage |

- Pro-Rib Ash Gray renders with metalness 0. Its roughness factor of 1.01 scales the texture's roughness map, whose mean is 0.40, so the average comes out at the catalog's 0.4: painted steel reads satin, not chrome.

![Pro-Rib Ash Gray, about 3 m from the eave (software WebGL)](img/prorib-close-1440.jpg)

**What a texture cannot do** (why the geometry step stays on the list):
- Ribs do not stand up at the eave or rake edge.
- A rib's shadow on the flat does not move with the sun.
- From 3 m the ribs read clearly. At grazing angles they flatten.

## Decision

**Keep the textures** for choosing a product in the studio.
- **019 geometry and 020 edge profiles:** real ribs, the metal ridge cap and rake trim in `roof-geometry.js` and `roof_core.py`. Do them in one session, with the `roof_qa.py` gate and a GPU close-up (local).
- **Blender:** it draws flat panels today. The studio's **Blender command** button says so on its hint.
