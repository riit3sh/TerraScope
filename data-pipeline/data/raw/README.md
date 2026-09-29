# RERA seed data

TerraScope matches parcels to registered projects by district using a static
CSV placed here. No dataset ships with the repository, so RERA evidence reads
"no RERA seed dataset is configured" until you supply one.

Drop a MahaRERA export (or any state export) at:

    data-pipeline/data/raw/maharera_seed.csv

Point `RERA_SEED_PATH` somewhere else if you keep it outside the repo.

The loader normalizes headers, so any of these spellings work:

| Field                        | Accepted headers                                                              |
| ---------------------------- | ----------------------------------------------------------------------------- |
| `district`                   | district, district_name, districtname                                          |
| `rera_registration_number`   | registration_number, registration_no, rera_registration_no, registrationnumber |
| `promoter_name`              | promoter, promoter_name, name_of_promoter                                      |
| `registered_completion_date` | completion_date, proposed_completion_date                                      |
| `source_url`                 | project_url, url, website                                                      |

Only `district` is required. Matching is exact and case-insensitive on the
district name, so a parcel near a registered project will not match if the two
sources spell the district differently.
