# Review round 3: the outline, the lidar-surface flag and what round 2 claimed

Date: 2026-11-16. Reviewer: an independent pass over the skill `rooftec-roof-measure` at tag `roof-measure-v3`.

**The short version.** The roof outline cannot be measured better than about 4 in (0.10 m) for $0, so the skill now prints a likely range with every area: plus or minus 2.3 to 4.4% on the benchmark houses. Lidar return counts separate a tree from a dormer cleanly, so the `lidar-surface` flag no longer fires on trees. Round 2's permit lookup, its site-check summary and its lidar decision all held up.

All scripts and outputs of this round are in the session scratch folder `review-r3/` (`work/o1c.py`, `o2c.py`, `o3b.py`, `o4.py` for the outline, `s1.py` for the flag, `c1.py` for the pitch rule, `k1.py` for slanted edges, `p1.py` and `p2.py` for permits, `v1.py` for the lidar spot check, `naip/chip.py` for the photos).

## 1. The outline

### Is "0.1 m is 2 to 4% of plan area" right?

Mostly. The exact figure is the length of the open roof edge (eaves and rakes, seen from above) times 0.1 m, over the plan area.

- On the 8 clean benchmark houses it is 2.3% (235246, a large hip roof) to 4.4% (175156, a small one).
- On 30 random houses from round 2 it is 2.5 to 5.3%.
- So "2 to 4%" understates small and cut-up roofs. The skill now computes the figure for each house.

### Can lidar place the roof edge better than round 2 said?

No. I measured the edge three ways on 38 houses (8 benchmark, 30 from round 2's random sample), on 145 straight open edges with a total length of 817 m. House averages use the 27 houses with 3 or more usable edges. "Offset" means lidar roof edge minus city outline; positive is outside the city line.

| Method | Eaves | Rakes |
|---|---|---|
| Point counts: midway between where single-return roof points stop and where all roof points stop | +0.04 m (standard error 0.014) | -0.05 m (0.034) |
| Same, with the tight height band round 1 and 2 used | -0.04 m (0.014) | -0.05 m (0.034) |
| Return intensity: the point where a roof return has lost half its strength | not usable (see gutters below) | -0.07 m (0.031) |

What this shows:

- **The city outline is the lidar roof edge within 0.05 m on average**, whichever method is used. No method puts it further off.
- **The method itself is only good to about 0.08 m.** One choice inside it, how far above the fitted plane a point may lie and still count as roof, moves the eave result from -0.04 to +0.04 m. Round 1 and 2 used the tight band, which drops edge pulses on steep roofs and made house 235247 (8 in 12) look worse than it is.
- **House to house, the outline is consistent.** The house averages scatter by 0.09 m, and 0.08 m of that is the noise of the lidar measurement (from the spread between the edges of one house). What is left for real differences between houses is about 0.04 to 0.05 m. Round 2's "scatter 0.07 m" was mostly lidar noise, not outline error.
- **A single edge is worse than the house average.** Edge offsets scatter by 0.15 m, and long edges are not much better than short ones (0.12 m above 12 m long, 0.18 m at 2 to 4 m). So eave and rake lengths carry about 1 ft of doubt per edge even when the area is fine.
- **Lidar sees gutters.** At eaves the intensity method reads 0.24 m further out than at rakes, because white aluminium gutters reflect far more than shingles. So the lidar "roof edge" at an eave includes the gutter where there is one, about 0.10 to 0.12 m beyond the shingles. Lidar cannot say whether the city line follows the shingle edge or the gutter lip. (Inference: eaves read 0.09 m further out than rakes against the city line, which fits a city line on the shingle edge and a lidar edge on the gutter.)
- **The laser spot is wider than the notes said.** The strength of a roof return fades over about 0.9 m across a rake. The spot is nearer 0.8 to 1 m than the 0.5 m round 1 inferred.

I also fitted a physical model of the pulse (Gaussian spot, detection threshold, edge scatter, a bright gutter) to the stacked profiles. The fitted eave position moved between 0.22 m outside and 0.40 m inside the city line depending on which parameters were free. That is a negative result: the data does not hold the answer.

One house stands out. On 235247 the main eave (14 m long) has no roof returns in the outer 0.25 m and the edge sits about 0.4 m inside the city line. The house average is -0.21 m with a standard error of 0.10, about two standard errors, so it is not proof. A per-house outline flag would have fired on this one house in 38; it was not built, because the lidar noise per house (0.08 m) is as large as the tolerance it would test.

### Can NAIP 2025 (0.3 m) do better?

No. I pulled the 28 July 2025 chips for six benchmark and sample houses from Microsoft Planetary Computer.

- The photo is not a true orthophoto. Roofs are shifted against the city outline by 0.3 to 1.5 m, more on taller houses. An absolute edge position is therefore useless.
- A width between two eaves of equal height is not affected by that shift. On the one clean case (the length of twin home 176864, bright roof against shadow at both ends) the photo gives 35.47 m and the city 35.62 m, a difference of 0.15 m, or half a pixel.
- On the other houses a tree (leaf-on in July), a shadow or low contrast made one of the two edges ambiguous by 1 to 4 pixels.

So NAIP agrees with the city outline within its own resolution and cannot narrow it. It is still useful for one thing: it shows trees, which confirmed the tree calls in section 2.

### Decision

Do not move any area. Report a range.

- The outline tolerance is set to 0.10 m (4 in). It covers the average offset (within 0.05 m), the real house-to-house spread (about 0.05 m) and the limit of the lidar method (0.08 m), combined as independent errors (0.105 m).
- The pitch part is 0.3 degree where lidar set the pitch and 1 degree where the city pitch was kept. It adds 0.1 to 0.4% on clean houses.
- Result on the 8 clean benchmark houses: plus or minus 2.3 to 4.4% of the sloped area. On the 30 sample houses: 2.5 to 5.4%.
- The plan's 2% area target cannot be confirmed from free data on any house in the set. Only a tape can do that.

**What to tape.** Measure one eave-to-eave width at the shingle edge, not at the gutter. If the city line is on the gutter lip, the tape will read 0.2 to 0.25 m (8 to 10 in) less than the model across a house with gutters on both sides. That single number would settle the largest open question in the error budget.

## 2. The `lidar-surface` flag

Round 2's flag fired on 3 of 8 clean benchmark houses. I looked at every flagged plane on 40 houses (9 benchmark, 31 sample): 20 planes on 14 houses.

| House, plane | What lidar shows | Verdict |
|---|---|---|
| 177261, plane 1 | 30% of points 4 m above the plane, all from pulses with several returns | A tree. The July 2025 photo shows it over the north plane. The roof is fine. |
| 235247, planes 3 and 4 | 14 to 17% of points 0.6 to 1.3 m above the plane, 6 to 15% from multi-return pulses | A solid surface the model lacks. True positive. |
| 176864, plane 0 | 28% of points 0.4 m below the plane, 2% multi-return | Real. Both end thirds of the plane lie 0.42 m lower than the middle; the model drew three roof sections as one face. Area is unaffected; two short steps are missing from the lines. |

The return count separates the two cases with a wide gap. Of the 13 planes flagged for points above the surface: 6 have 83 to 100% multi-return points sitting 2.4 to 6 m up (trees), 6 have 0 to 15% sitting 0.5 to 1.3 m up (solid), and 1 is mixed (57%, on house 199138, which has an addition permit). Nothing falls between 15% and 57%. The photo of 177353 and 219266, both "solid", shows no tree near the flagged plane.

**Verdict: keep the flag, and split it.** The cached points now keep the return count (one more small array). A plane whose off-surface points are 80% or more multi-return raises the new `tree-over-roof` info flag, which asks for nothing. 30% or less raises `lidar-surface` with the words "solid surface". In between, or with points cached before this round, the old wording stays. On the benchmark the flag now fires on 2 of 8 clean houses, both real model errors, and on 8 of 31 sample houses (it was 10 with trees).

## 3. Round 2's other changes

- **Permit matching is right.** On 30 random houses every permit point sits exactly on a city address point (distance 0.0 ft), and the address point of the house is on its footprint on 8 of 8 houses checked. Permits found on a footprint always carry one address; permits in the bounding box that belong to a neighbour were dropped every time.
- **No false alarms.** None of the 30 houses has a watched permit since 2023. The class `New%` matches only new houses, town homes and duplexes; sheds and accessory buildings have classes of their own.
- **What it ignores.** Since January 2023 the city issued 4,036 residential `Repair` and 3,059 `Remodel/Renovation` permits; 5 of the 30 random houses have one. Making them site checks would block about one house in six for work that rarely touches the roof line. They are now an `info` flag, `permit-other`.
- **A real gap: the cache never expired.** The permit answer was cached for ever like every other city answer, so a permit issued after the first run was never seen. It is now asked again after 30 days, and the old answer is used when the service is down.
- **`siteCheckRequired`** is set on every blocked benchmark building and reaches the report headline and the GLB.
- **The `IncompleteRead` retry** is correct: the exception is an `http.client.HTTPException`, which the retry loop now catches, and a test covers it.
- **`PREFER_LIDAR`, spot check.** Five of round 2's 30 houses, picked with a fixed seed (211149, 236313, 234133, 201990, 220518), fitted with my own reader (laspy and pyproj) and my own trimmed least-squares fit. On 16 precise main planes my pitch is within 0.15 in 12 of a whole number on 14 and the city's on 9; lidar is 0.14 in 12 steeper on average; my fit and the skill's differ by 0.11 at most. Round 2's result stands.

## 4. Pitch: a narrow version of "one house, one pitch"

Round 2 reported that city pitches of imprecise planes are 0.40 in 12 from the house's common pitch and lidar 0.17. I could not reproduce that size. On 71 imprecise planes that have a precise plane of similar pitch on the same house, the city is 0.26 in 12 away on average and the plane's own lidar pitch 0.22. For small planes (under 215 sq ft) it is 0.29 against 0.26. That is no case for a general rule.

A narrow rule does hold. Nine planes fail the "precise" test only because fewer than 80% of their points lie on one plane; their standard error is small. For 4 of the 9 the lidar pitch is within 0.5 degree of a precise plane on the same house. On all 4 the lidar pitch is close to a whole number (0.09 in 12 away on average) and the city pitch is not (0.29 away): 4.66 against 4.86, 3.83 against 4.03, 2.81 against 2.98 and 7.45 against 7.85. The skill now uses the lidar pitch on such planes. It does not touch planes whose fit is imprecise for lack of points.

## 5. Open edges that are neither eave nor rake

An open edge is called a rake when it runs more than 10 degrees off the level line of its plane. Many such edges run less than 45 degrees off it: 14 of 39 houses (8 benchmark, 31 sample) have 10 ft or more of them.

- On 4 edges (3 houses) lidar shows the plane faces 11 to 16 degrees away from the city model, and the edge is level in lidar within 2 degrees. Those are eaves on a plane the model drew askew.
- On the rest lidar agrees with the model's direction. The edge really runs at a slant across the plane in the model, most likely where the model merged the facets over an angled wall.

Water runs off all of these edges. The skill does not re-class them without a photo or a tape; it now raises `skewed-edge` (review, from 10 ft) and `lidar-azimuth` (review, a plane 8 degrees or more off the lidar direction).

## Not checked in this round

- Any roof against a tape or a paid report. Still the one check that can make a number `verified`.
- Whether the city line is the shingle edge or the gutter lip (section 1).
- The 1 January 2023 permit cut-off.
- The studio import in a browser. The geometry of three benchmark houses changed by a re-tilt; the GLB area equals `roof.json` within 0.004% on all 12 houses and 0.6% on City Hall, as before.
