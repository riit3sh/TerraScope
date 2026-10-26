# Legal verification: official sources, what TerraScope does, and the manual workflow

Researched 2026-10-26. Tamil Nadu first. **No legal check is automated for any state.** BUY still requires all four
mandatory checks (title, encumbrance, zoning, approvals) positively verified by a matched official record, and no such
record source is integrated, so live analyses never reach BUY.

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
