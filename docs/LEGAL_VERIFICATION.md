# Legal verification: official sources, what TerraScope does, and the manual workflow

Researched 2026-10-26. Tamil Nadu first. **No legal check is automated for any state.** Since 2026-10-27 a strong
location is "BUY only after the legal checks": title, encumbrance, zoning and approvals are never treated as verified
without a matched official record, they stay the first thing to do before paying, and a defect found is WALK AWAY.

## Tamil Nadu sources

| Check | Official source | What it holds | Access | Automation |
|---|---|---|---|---|
| Title / ownership | Commissionerate of Land Administration e-Services, [eservices.tn.gov.in](https://eservices.tn.gov.in/) | Patta / chitta, A-register extract, FMB sketch, TSLR extract (urban); verification of web-issued copies by reference number | Public web form: district, taluk, village, survey and subdivision number (or patta number / owner name) | No published API; robots.txt returns 403. Not scraped. Patta is revenue ownership, not the full title chain |
| Encumbrance (EC) | Registration Department, [tnreginet.gov.in](https://tnreginet.gov.in/portal/) | Registered sales, mortgages, leases and attachments on a survey number, by period | Online search with a captcha; some services need a user account (third-party guides disagree on which) | No published API; captcha must not be bypassed. Unregistered agreements are absent |
| Zoning / land use | Directorate of Town and Country Planning, [tcp.tn.gov.in](https://tcp.tn.gov.in/); CMDA, [cmdachennai.gov.in](https://cmdachennai.gov.in/) in the Chennai metropolitan area | Master plans and local planning area plans | Plan documents and maps; land-use certificate from the authority | No parcel lookup or API found |
| Layout / building approvals | Single window portal for planning permission, [onlineppa.tn.gov.in](https://onlineppa.tn.gov.in/) (DTCP, CMDA, local bodies) | Planning permission applications and approvals | Applicant portal | No public search by survey number or API found |
| RERA | TNRERA, [rera.tn.gov.in](https://rera.tn.gov.in/) | Registered projects (building, normal layout, regularisation layout), status | Public listing pages | No published API; robots.txt disallows `/uploads/` and PDFs. Registration does not prove title |
| Spatial reference | TNGIS, [tngis.tn.gov.in](https://tngis.tn.gov.in/) (Tamil Nilam GI viewer) | Village / cadastral viewer | Registration with captcha for some features; an `api.html` page exists but documents nothing | Not usable until TNGIS documents an API and its terms (contact tngis.support@tn.gov.in) |

Not found: published terms of use or automation policies on these portals. Absent a documented API and terms, none
are automated or scraped. Third-party aggregators (for example sites republishing planning permissions or RERA lists)
are not official records and are not used.

## What TerraScope does

- **State guide** (`backend-api/routers/legal_checks.py`, `STATE_GUIDES`): for each check, the official source, how to
  search it, and its access limits. Only Tamil Nadu has a guide. Any other state shows "no state guide yet" and the
  generic checklist; nothing implies it is covered. Adding a state means adding one researched entry, with
  `automated_sources` staying empty until a permitted source exists.
- **Manual record** (`POST /api/v1/parcels/{id}/legal-checks`, append-only table `legal_checks`): outcome (record found
  and matches the seller / problem found / could not find the record / not applicable, RERA only), source consulted,
  date checked, reference number, evidence document, notes. Earlier records are kept; the newest per check is shown.
- **Three states, never mixed:**
  - automated verification: none today (would be a matched `land_records` entry);
  - recorded by you: shown with the date and source, labelled "not verification by TerraScope";
  - not checked.
- **Effect on the decision:** a recorded problem is adverse evidence and gives WALK AWAY, and the findings list shows it
  as a red flag. A recorded confirmation is named in the reasoning ("you recorded it as checked on …; TerraScope cannot
  verify that") but never satisfies a BUY requirement. "Could not find the record" is pending, never a clearance.

## Manual workflow for a buyer (Tamil Nadu)

1. Get the survey number, subdivision, village, taluk and district from the seller, and enter them under Survey
   details.
2. Patta / chitta and A-register on e-Services: the owner must be the seller; save the copy and upload it.
3. EC on TNREGINET for at least 30 years: list every transaction; any mortgage or attachment not closed is a problem.
4. Land-use zone from the DTCP / CMDA plan or a land-use certificate.
5. Layout approval number and the approved layout plan, confirmed with the issuing office.
6. RERA, if a promoter sells the plot in a layout.
7. Record each check in the report, then have a lawyer review the title chain before paying.

## Government, public-facility and restricted land

**Two kinds of evidence, never mixed:**

| Kind | Source | What it can say | What it cannot say |
|---|---|---|---|
| Mapped | OpenStreetMap public-facility store per region (`data-cache/regions/<region>/public_land.sqlite`) | A court, government office, government school or hospital (by name or operator tag), stadium or sports ground, park, railway land / station / line, defence area, protected area, burial ground or water body overlaps, touches or is near the boundary | Who owns the land. A stadium is a sports facility; its owner is unknown unless a record says so |
| Official record | Checked by the buyer and recorded (`government_land` check): Tamil Nadu e-Services "Verify Government (Poramboke) / Private Land", A-register, FMB sketch, taluk office orders | Government (non-transferable), government with a documented lawful auction or transfer, private per that record, a restriction that prohibits the use or allows it on conditions, or record unavailable | A full title: one record is not a title guarantee |

- **Official access:** the e-Services verification is a public web form (district, taluk, village, survey and
  subdivision number), with no published API. It is not automated, scraped or captcha-bypassed. TNGIS has no
  documented API. No authoritative public-land (cadastral / poramboke) geometry is available for any state, so a
  mapped overlap is always "potential", never "confirmed".
- **Contact** is measured on the parcel polygon:
  - overlap: at least 200 m² or 5 % of the plot, or a railway line crossing it;
  - a facility point inside the plot;
  - edge: touching, or within the ±15 m positional uncertainty;
  - nearby: within 2 km.
- **Status and effect** (decided before any score, so a high location or development score cannot override it):
  - confirmed government (non-transferable), or a restriction prohibiting the use → **WALK AWAY**;
  - documented lawful transfer or auction, a restriction with conditions, conflicting records, potential public land
    (map only) → at most **WAIT**, with the warning first in the summary;
  - private per the record checked → no hold, unless the map shows an overlap (then a surveyor's boundary check);
  - records unavailable / ownership unverified → never read as private.
- **Coverage:** public-facility stores are built for Tamil Nadu and Andhra Pradesh (2026-10-26, from the 2026-10-04
  Geofabrik extract). Other states report "not built", which is not evidence of anything. Build one from an installed
  region's extract with `python data-pipeline/fetch_data.py <region> --public-land`.
- **Licence:** OpenStreetMap data, ODbL 1.0. The store is a derived database: fine for local use; publishing it requires
  ODbL attribution and share-alike.

## Official portal links for other states (2026-10-27)

`docs/datasets/official_portals.json` holds the only links TerraScope shows outside Tamil Nadu's detailed guide:

- **RERA:** MoHUA's list of State/UT RERA authorities
  (https://rera.mohua.gov.in/real-estate-regulatory-authorities-of-states-uts.html).
  - 30 regions have a portal link, including shared ones: Andaman & Nicobar → Tamil Nadu RERA; Chandigarh → the Delhi
    RERA website; Dadra & Nagar Haveli and Daman & Diu → MahaRERA; Lakshadweep → Kerala RERA.
  - Arunachal Pradesh, Manipur, Mizoram, Nagaland, Sikkim and Ladakh are listed as "Website Not Setup", and the report
    says so.
- **Land records:** no authoritative national list was reachable (dilrmp.gov.in serves an incomplete certificate
  chain). A state portal is listed only if, on 2026-10-27, it was on a gov.in / nic.in domain and answered with a
  land-records or revenue page. That holds for 13 regions: AP, BR, CT, GJ, HR, KA, MH, OR, PB, RJ, TN, TG and UP. The
  other 23 get "ask the taluk / tehsil office" rather than an unchecked link.
- **What the report says:**
  - RERA has four states, never mixed: registered (matched record), recorded by you, no matching record (not proof
    the project is unregistered), and not applicable.
  - The applicability rule is RERA Act s. 3(2): projects on up to 500 m² or up to eight apartments are exempt unless
    the state sets lower limits.
  - Rainfall waterlogging and coastal flooding are separate rows, each NOT ASSESSED. A link is where to check, never
    verification.

## RERA verification workflow (2026-10-27)

- **Who is selling.** The report asks; the answer is stored with the land details (`seller_type`).
  - **Developer / promoter:** the finding flags that registration is likely required unless the project is exempt.
  - **Individual resale:** the finding says RERA may not apply to an ordinary resale, but it is never marked exempt
    automatically.
  - **Not sure:** the status stays unknown, with how to find out.
- **Official portal.** The RERA state is prefilled from the parcel and can be changed. "Verify on official portal"
  opens the authority's site from `docs/datasets/official_portals.json` (MoHUA's list, all 36 regions). Where MoHUA lists
  "Website Not Setup", the report says so and points to the state housing department. Opening a portal verifies
  nothing.
- **What the buyer records** (append-only, alongside the other legal checks): registration number, project, promoter,
  RERA state, the portal used, the date, notes and evidence. The outcome is one of:

  | Outcome | Meaning | Effect |
  |---|---|---|
  | Matching registration found | The buyer reports a matching project record | "Recorded by you, not verified by TerraScope"; a registration does not prove clear title |
  | Registration not found in search | No matching record appeared | Never "not registered". Flagged (caution) when a promoter is selling, to verify before paying |
  | Unable to verify | Portal unavailable or inconclusive | Status unknown |
  | Not applicable | The buyer records that RERA does not apply, with an optional reason | Recorded as theirs, with the statutory explanation |

- **What the outcomes never do.** RERA never decides BUY or WALK AWAY on its own. A registration number's format is
  never treated as verification. Only a matched record from an integrated official source would show "Registered
  (matched record)", and none exists today. Records made before 2026-10-27 ("confirmed", "not found") still read.
- **Statute (RERA Act 2016).**
  - s. 3(1): a promoter may not advertise or sell plots or apartments in a project without registration.
  - s. 3(2): exempt are land up to 500 m² or up to eight apartments (a state may lower these), and projects with a
    completion certificate before the Act.

### Future work: automated RERA verification

Not attempted: thirty-odd separate portal scrapers would be fragile and are not permitted. Automated verification
becomes possible if MoHUA's unified RERA portal (rera.mohua.gov.in), or an individual authority, provides a permitted
API or an official downloadable dataset of registered projects. Matching a drawn plot to a project would further need
project boundaries or survey numbers in usable form. No authority has been contacted, and no account or credential has
been requested.
