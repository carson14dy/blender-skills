# Next steps after advisor review

**Written:** 2026-11-16. **Reviews:** the five-step plan proposed after the Studio Lab tests.

## Best plan: yes, with changes

The proposed plan has the right core: fix the "verified" label, prove the numbers against a tape, and stop adding tools. It needs five changes.

1. **Start the accuracy study first, and run the fixes beside it.** Your part of the study (finding past jobs) is the slow part, so it starts today. Claude does the label fixes while you look.
2. **Do not call anything "verified" after 5 roofs.** Five roofs can catch a big error. They cannot prove a 2% claim. The study becomes two stages: 5 roofs now, 20 roofs over the season.
3. **Fix privacy and backup before anything else is built.** The GitHub repository is public, and a real street address is in it. The lab studio exists only in a temporary folder and a claude.ai page.
4. **Cut the 3D neighbourhood, the mesh merge and the public website from this round.** None of them makes a quote faster. Replace them with one real quote, start to finish.
5. **Decide where customers will see this before hosting anything.** The plan for the studio already says the customer product is the Rooftec app (`SiouxFallsApp`), not a second website.

## The revised plan

Total: about 4 to 6 hours for you and about 12 to 14 hours for Claude.

| # | Step | Who | Hours |
|---|---|---|---|
| 1 | Pick 5 past jobs for the study | You | 0.5 |
| 2 | Protect the work and the address | You, then Claude | 0.1 + 1.5 |
| 3 | Honest labels in the studio | Claude | 3 |
| 4 | Email the city GIS office | You | 0.25 |
| 5 | Accuracy study, stage 1 (5 roofs) | You, then Claude | 1 to 3 + 2 |
| 6 | One real quote, start to finish | Claude, then you | 5 to 7 + 0.5 |
| 7 | Decide where customers see it | You with Claude | 0.5 |
| 8 | Accuracy study, stage 2 (up to 20 roofs) | You, a little per job | 0.25 per job |

### Step 1. Pick 5 past jobs (you, 30 minutes)

- **Do:** write down 5 addresses inside city limits, built before 2020, for which you hold a paid measurement report or your own tape numbers. Aim for two simple roofs, two with valleys and one cut-up roof. Add the studio's measured house as a sixth if you can get to it.
- **Done when:** the list of addresses and where each "truth" number comes from is in a note that stays out of git.
- **Why first:** everything else can wait on Claude, but only you can do this, and it decides whether the tool can be trusted at all.

### Step 2. Protect the work and the address (you 5 minutes, Claude 1.5 hours)

- **Do (you):** decide whether `carson14dy/blender-skills` becomes private, or whether the studio's measured house address is yours to publish. Approve a push.
- **Do (Claude):** copy the lab studio from the temporary folder into the repository, push the tags `roof-measure-v1` to `v6`, and keep customer addresses out of every committed file from now on.
- **Done when:** a fresh clone of the repository holds the lab studio and the six tags, and no committed file names a customer's address unless you allowed it.
- **Why here:** the temporary folder can be wiped at any time, and a public address cannot be taken back later.

### Step 3. Honest labels in the studio (Claude, 3 hours)

- **Do:** show the data credit; change "Verified: 4 independent reviews" to "Estimate, not yet checked against a tape"; show the ± range beside every number; open on the measured job.
- **Done when:** the word "verified" appears nowhere in the studio, the report or `detail.json`, and the credit line is on screen with every measured job.
- **Why here:** it does not depend on the study, it is cheap, and a review by an AI is not a check against a tape.
- **Left out on purpose:** the lighter 3D file. It only matters for AR and sharing, which are deferred.

### Step 4. Email the city GIS office (you, 15 minutes)

- **Do:** send the draft at the end of this file to cityofsfgis@siouxfalls.gov.
- **Done when:** the email is sent. The reply is not needed for steps 5 or 6.
- **Why here:** the reply can take days, and it decides whether showing city buildings on a public page is allowed.

### Step 5. Accuracy study, stage 1 (you 1 to 3 hours, Claude 2 hours)

- **Do (you):** write one small truth file per roof (10 minutes each). Where you can, tape one eave-to-eave width and one rake length from the ground, and note whether there are gutters. Do not walk a winter roof.
- **Do (Claude):** write the pass rule into the skill before running anything. Then run `measure` and `compare` on each roof, and run the skill on the studio's measured house to compare it with the hand-fitted model.
- **Done when:** an error table for all 5 roofs is in `references/validation.md`, with a plain "pass" or "fail" against the rule below.
- **Why here:** it is the first step that needs your list from step 1.

**Stage 1 pass rule (my recommendation; it changes the skill's written rule):**

1. On every roof, the true area falls inside the range the tool printed.
2. No roof is more than 3% off on area, and the average error is within 1.5% either way.
3. The main pitch is within 1/4 in 12 on every roof.
4. Each line total (ridge, hip, valley, eave, rake) is within 3% or 2 ft on at least 4 of 5 roofs.
5. A pass earns the label "checked on 5 roofs". It does not earn "verified".

On a fail, stop studio work and look at which part failed (outline, pitch or line classes) before doing anything else.

### Step 6. One real quote, start to finish (Claude 5 to 7 hours, you 30 minutes)

- **Do (Claude):** connect the skill to the studio's priced list, so that an address gives a takeoff and a priced materials list for both stores. Refresh the store prices first.
- **Do (you):** on your next 3 leads, run it beside your normal method. Write down the minutes each way and the difference in squares.
- **Done when:** one real address goes to a priced list in under 10 minutes of your time, and you have 3 side-by-side comparisons.
- **Why here:** this is where the money is. A faster quote and a saved report fee or site visit pay back before any 3D polish does.

### Step 7. Decide where customers see it (you with Claude, 30 minutes)

- **Do:** choose one: show it in person on your own phone or tablet; port it to the Rooftec app; or host a page that needs a login.
- **Done when:** one sentence is written at the top of `lab/projects/sioux-falls-studio/PLAN.md` saying where customers see it.
- **Why here:** steps 5 and 6 tell you whether it is worth showing, and the city's reply tells you what may be public.

### Step 8. Accuracy study, stage 2 (you, 15 minutes per job)

- **Do:** on every job you actually roof, tape one eave and one rake, and add a truth file.
- **Done when:** 20 roofs are in the table.
- **Why last:** it runs in the background of real work and costs almost nothing per job.
- **"Verified" rule:** at 20 roofs, at least 18 are within 3% on area, none is outside 5%, and the average error is within 1%.

## Answers to the five questions

### 1. Is the order right, and is the study big enough?

- **Order:** the study should start before the quick fixes, because your part has the longest wait. The honesty fixes do not depend on the study, so they run in parallel.
- **Size:** 3 to 5 roofs is a smoke test, not proof. If the tool were within 2% on only half of all roofs, it would still pass "4 of 5" about 1 time in 5. With 5 clean roofs you can only say that fewer than about 60% of roofs fail. With 20 clean roofs that drops to about 15%.
- **Threshold:** the tool's own error budget says free data cannot place the roof edge better than 2 to 5% of the area. A 2% pass line is therefore partly luck. A 3% line matches the business: 3% of a 25-square roof is under one square, which the normal waste allowance covers. *(The link to waste allowance is my inference.)*
- **Truth:** a paid report is a reference, not the truth. A tape at the shingle edge is the truth. At least 2 of the 5 roofs need a taped width.

### 2. What is missing?

1. **The money path.** The plan has no step where a real quote gets made. The priced list (studio step 017) is already built; nothing connects the measuring skill to it.
2. **Two measuring methods.** The studio's "verified" house was hand-fitted from 36 photos. The skill is a different, automatic method. The proposed study tests only the skill, yet the studio shows the other one. They differ by about 2% on that house (2,388 against the city's 2,340 sq ft).
3. **Privacy and licence.** The repository is public *(verified)*. Free GitHub Pages also needs a public repository *(my recollection of GitHub's terms, not re-checked)*. The city data is "not intended for use in mapping products for resale"; quoting in-house is fine, but a public page that serves 97 neighbours' buildings is closer to the line.
4. **Staleness.** Store prices are from 15–16 November and change weekly. The city model is from June 2023 and the lidar from December 2020. About 1 house in 7 needs a site check. A quote needs a price refresh and the date printed on it.
5. **The real app.** `SiouxFallsApp` is not in this repository, so I could not check it. The studio plan says to port steps 016–018 there. Hosting the studio would create a second customer product.

### 3. What to cut or defer

1. **3D Tiles neighbourhood on every job (1 to 2 days).** It looks good and sells nothing yet. It also raises the licence question.
2. **Merging the 375 meshes (half a day).** Those meshes belong to the one hand-built house. Roofs from the skill are simple models. *(Inferred; I did not count draw calls on a skill roof.)*
3. **The lighter 3D file and AR.** Defer until a homeowner asks to see the roof on their own phone.
4. **The public website.** Defer until step 7 is decided.
5. **Still skipped:** WebGPU, splats, Unreal, Twinmotion, and also Blender look-dev (step 021) and experiments 029 to 034.

### 4. Are the time estimates realistic?

- **Quick fixes, 4 hours:** fair for the lab copy. Allow 5 to 6 hours once the changes also go into the real studio on `rooftec-lab`. *(Inferred.)*
- **Study, 2 to 4.5 hours:** fair only if you already hold reports. Taping adds about 1 hour per roof plus travel, and it is winter. Expect days of calendar time.
- **Steps 3 and 4 of the proposed plan had no hours.** The lab report puts them at up to 2.5 days plus hosting. That is more than everything else in the plan combined.

### 5. Risks the plan ignores

1. **Loss of work.** The lab studio is in a temporary folder, and the six version tags were never pushed.
2. **A customer's address in public.** It is in four committed files today and would be on any public website.
3. **A false "verified".** Flipping the switch after 5 roofs would put that word on customer documents with little behind it.
4. **A stale quote.** Prices change weekly, and Menards blocks automatic refresh, so a refresh there is partly by hand.
5. **One free source.** The city service has no promise of staying up or unchanged. Keep each job's `roof.json` so old jobs never need a second download.

## Not checked

- Whether the studio's measured house is a customer's house or your own.
- What `SiouxFallsApp` already does; it is not in this repository.
- The licence reading; it is not legal advice.
- Current GitHub Pages terms for private repositories.

## Draft email for step 4

> Subject: Questions about the 3D Building Wireframe layer
>
> Hello. I run a roofing business in Sioux Falls and use the city's 3D Building Wireframe and Building Footprints layers to estimate roof sizes for my own quotes. I have four questions.
>
> 1. Who produced the June 2023 3D building model, and what is its stated accuracy?
> 2. Does the footprint outline follow the roof edge or the gutter edge?
> 3. Is a bulk download available?
> 4. The licence says the data is "not intended for use in mapping products for resale". Is it acceptable to show a customer a 3D view of their own house, with a few neighbouring buildings for context, on a web page, with the credit line shown?
>
> Thank you.

## First action (20 minutes)

Open your past-job folder and write down 5 addresses that have a measurement report or tape numbers. Stop there. That is step 1 done.
