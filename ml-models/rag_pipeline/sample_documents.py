"""Hand-authored documents standing in for Review 2 document ingestion."""

SAMPLE_DOCUMENTS = [
    {
        "text": (
            "Certified extract from Survey Record 7/12, Pune District, dated 14 March 2024. "
            "The parcel identified as Survey No. 118/2A is recorded in the names of Anil Prakash "
            "Kulkarni and Meera Anil Kulkarni. The tenure is shown as private occupancy land. "
            "The extract lists no mutation objection in the latest available entry."
        ),
        "source_type": "land_record",
        "source_reference": "pune-7-12-survey-118-2a-2024",
        "parcel_id": "parcel-pune-001",
    },
    {
        "text": (
            "Talathi office note dated 22 April 2024 for Survey No. 118/2A, Haveli Taluka. "
            "A search of the supplied village record indicates one historical bank charge released "
            "in 2019. The release entry should be checked against the original registered deed before "
            "a sale agreement is signed. No current encumbrance is shown in this extract."
        ),
        "source_type": "land_record",
        "source_reference": "pune-talathi-encumbrance-note-118-2a",
        "parcel_id": "parcel-pune-001",
    },
    {
        "text": (
            "MahaRERA-style registration notice, registration number P52100041234, for Green Ridge "
            "Residency by Kaveri Habitat LLP, Pune district. The project is registered for residential "
            "development with a declared completion date of 30 September 2027. The notice names Kaveri "
            "Habitat LLP as promoter and records the project status as registered, subject to ongoing "
            "quarterly disclosures."
        ),
        "source_type": "rera_notice",
        "source_reference": "maharera-P52100041234-registration-notice",
        "parcel_id": "parcel-pune-001",
    },
    {
        "text": (
            "MahaRERA-style quarterly disclosure dated 10 January 2025 for Green Ridge Residency. "
            "The promoter reports that the registration remains active and that construction has reached "
            "the plinth-stage milestone. This notice is a project-level record and does not by itself prove "
            "clear title to any privately held adjoining parcel."
        ),
        "source_type": "rera_notice",
        "source_reference": "maharera-P52100041234-quarterly-disclosure-2025-01",
        "parcel_id": "parcel-pune-001",
    },
    {
        "text": (
            "Government of Maharashtra Urban Development Department notification UDD-2024/CR-88, issued "
            "6 June 2024. The notification proposes a traffic-capacity improvement study for the Pune ring "
            "road corridor and requests a feasibility report from the regional transport authority. It is a "
            "planning notification, not a sanction or guarantee that construction will occur at a particular parcel."
        ),
        "source_type": "government_notification",
        "source_reference": "maharashtra-udd-2024-cr-88-ring-road-study",
        "parcel_id": "parcel-pune-001",
    },
    {
        "text": (
            "Land record abstract for Survey No. 42/1, Mulshi Taluka, Pune district, downloaded 8 February 2024. "
            "The recorded holder is Shantaram Dattatray Jagtap. The land-use remark is agricultural and the "
            "abstract does not include a development permission. The document advises obtaining a current "
            "certified 7/12 extract and property card before relying on ownership information."
        ),
        "source_type": "land_record",
        "source_reference": "pune-mulshi-7-12-survey-42-1-2024",
        "parcel_id": "parcel-pune-002",
    },
    {
        "text": (
            "Sub-registrar search note for Survey No. 42/1 dated 12 February 2024. The search summary lists "
            "a 2016 family partition deed and no registered sale deed after that instrument in the supplied "
            "period. The note is not a legal title opinion and recommends a full chain-of-title review."
        ),
        "source_type": "land_record",
        "source_reference": "pune-mulshi-subregistrar-search-42-1",
        "parcel_id": "parcel-pune-002",
    },
    {
        "text": (
            "MahaRERA-style search result dated 1 February 2025 for Survey No. 42/1, Mulshi Taluka. No matching "
            "registered project number was found in the supplied seed search. This result is not evidence that the "
            "land is free of all development proposals; it only records that no matching RERA project was present "
            "in this search result."
        ),
        "source_type": "rera_notice",
        "source_reference": "maharera-seed-search-mulshi-survey-42-1-2025",
        "parcel_id": "parcel-pune-002",
    },
    {
        "text": (
            "District planning circular DP-2023/17, Pune, dated 19 December 2023. The circular asks local offices "
            "to map watercourse buffers and retain access to existing village roads during layout review. It does "
            "not determine title, project registration, or final development permission for Survey No. 42/1."
        ),
        "source_type": "government_notification",
        "source_reference": "pune-district-planning-circular-2023-17",
        "parcel_id": "parcel-pune-002",
    },
]

