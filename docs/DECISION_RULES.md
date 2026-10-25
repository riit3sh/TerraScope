# TerraScope decision rules

TerraScope answers one question for a drawn plot: **BUY, WAIT, WALK AWAY, or INSUFFICIENT DATA?** The engine is
deterministic (`ml-models/scoring_engine/_verdict.py` and `_assessment.py`), and every rule is unit-tested. AI text, when
a Groq key is configured, only explains the result; it never changes it. There is no price, appreciation or demand
prediction.

Stored codes: `BUY`, `WAIT`, `AVOID` (shown as WALK AWAY) and `INSUFFICIENT_EVIDENCE` (shown as INSUFFICIENT DATA). The
codes are kept so saved reports still read.

## Order of decision

1. **WALK AWAY on proven legal risk.** Only possible when matched land records exist; none are integrated, so this never
   fires today.
2. **WALK AWAY on a red flag** from the plot's history (below). A verified serious risk is never offset by good access
   or growth.
3. **INSUFFICIENT DATA** when a weighted location factor (area growth or road/school access) has no evidence.
4. Otherwise the **location score** = weighted mean of the scored location factors (your profile's weights). It is a
   rule-based score, not a probability of success or appreciation.
5. **BUY only when the location score is 75 or more AND the legal due diligence is verified** (title, encumbrance,
   zoning and approvals from matched land records). History alone never makes a BUY. Unknown legal status is never
   treated as safe: a strong location with unverified legal checks is **WAIT**, naming the pending checks. No land-records
   source is integrated today, so in practice the best answer is "WAIT: location strong, legal checks pending".
6. A WAIT names what holds it back. Every answer lists **what would change it** (`verdict.would_change`).

Unverified legal safety appears on every report as "before you pay" checks.

## Rules

| Rule | Evidence | Why it matters | Effect | When evidence is missing | Validated? |
|---|---|---|---|---|---|
| River-flood red flag | JRC river flood hazard maps v2.1.2 (modelled, ~90 m) | Frequent river flooding of the plot itself | WALK AWAY if modelled flooding covers ≥25% of the plot at 1-in-100 years or more often | River flooding "Unknown"; no red flag is raised and no safety is assumed | Provisional (25%, 1-in-100) |
| Water-bed red flag | JRC Global Surface Water 1984-2021 (observed, 30 m) | A plot that held water may be a tank, lake or river bed | WALK AWAY if water was seen in ≥10% of satellite passes on average | "Unknown" | Provisional (10%) |
| Wet-plot red flag | Esri / Impact Observatory land cover 2017-2023 (10 m) | The plot itself mapped as water | WALK AWAY if any year shows water or flooded vegetation | Not raised | Provisional |
| Area development (rate) | Same land cover: built-up share within 1 km, per year 2017-2023; least-squares trend over every year | New building nearby is evidence of development reaching the area | Score = trend ÷ 2 points a year × 100 (capped 0-100) | INSUFFICIENT DATA (it is a location factor) | Provisional (2 points a year) |
| Established area (level vs rate) | Same | A ring already ≥75% built with under 0.5 points a year of new building is an established neighbourhood, not a stagnant one | Area development is described but **not scored** for or against; the decision rests on access and risks | — | Provisional (75%, 0.5) |
| Road and school access | Regional OpenStreetMap store (straight-line distance from the drawn boundary) | Day-to-day usability | Each sub-score falls linearly to 0 at your limit (default road 3 km, school 5 km); weighted by property type and importance | INSUFFICIENT DATA, with the exact `terrascope.cmd fetch-data <region>` to fix it. A road or school that OpenStreetMap has not mapped is **unknown, not absent**: it is left out of the score and the buyer is asked to check locally | Provisional; limits are yours to set |
| Flood safety (score) | — | No validated method combines the flood mechanisms | Never scored; evidence feeds only the red flags | Rainfall waterlogging and coastal flooding are "Unknown" | — |
| Legal safety | Land records (none integrated) | Title, encumbrance, approvals | Scored only from matched records; otherwise "before you pay" checks | "Unknown", never clear | — |
| RERA | State RERA authority (not integrated) | Applies to plots sold in a promoter's layout | Not scored | "Unknown"; check the state portal | — |

**News** (GDELT, on demand, cached 24 h) and **development claims** (recorded by the buyer, from residents, brokers or
sellers) never change the decision. News is discovery evidence: an official source, a story corroborated by two or more
outlets, or a single report, with proposals and items older than 2 years labelled. It cannot verify title, prove that no
dispute exists, or show a plot is flood-safe. Claims stay "not verified" until official evidence is checked, and no
completion date or appreciation is assumed.

Hospitals, bus and railway stations are shown with distances for the buyer to weigh; they are not scored, so a plot is
never rated up for simply having more facilities nearby. Colleges, markets and shops are not collected in this version.

None of the thresholds has been calibrated against outcomes (sales, floods, disputes). They are explicit and documented
so they can be challenged; they were not tuned to produce more BUY results.
