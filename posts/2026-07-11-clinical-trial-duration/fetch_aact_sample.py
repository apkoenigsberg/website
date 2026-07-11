# Pull completed interventional Phase 2/3 trials from ClinicalTrials.gov API v2
# and flatten to trials.csv. No API key required.
import csv
import time
import requests

BASE = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = [
    "protocolSection.identificationModule.nctId",
    "protocolSection.designModule.phases",
    "protocolSection.designModule.enrollmentInfo",
    "protocolSection.designModule.studyType",
    "protocolSection.statusModule.startDateStruct",
    "protocolSection.statusModule.primaryCompletionDateStruct",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor",
    "protocolSection.conditionsModule.conditions",
    "protocolSection.contactsLocationsModule.locations",
]
PARAMS = {
    "filter.overallStatus": "COMPLETED",
    "query.term": "AREA[StudyType]INTERVENTIONAL AND (AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)",
    "fields": ",".join(FIELDS),
    "pageSize": 1000,
}
MAX_PAGES = 12  # ~12k studies

rows = []
token = None
for page in range(MAX_PAGES):
    params = dict(PARAMS)
    if token:
        params["pageToken"] = token
    resp = requests.get(BASE, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    for st in data.get("studies", []):
        proto = st.get("protocolSection", {})
        design = proto.get("designModule", {})
        status = proto.get("statusModule", {})
        enroll = design.get("enrollmentInfo", {})
        locs = proto.get("contactsLocationsModule", {}).get("locations", []) or []
        countries = {l.get("country") for l in locs if l.get("country")}
        rows.append({
            "nct_id": proto.get("identificationModule", {}).get("nctId"),
            "phases": "|".join(design.get("phases", []) or []),
            "enrollment": enroll.get("count"),
            "enrollment_type": enroll.get("type"),
            "start_date": status.get("startDateStruct", {}).get("date"),
            "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
            "sponsor_class": proto.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("class"),
            "n_conditions": len(proto.get("conditionsModule", {}).get("conditions", []) or []),
            "n_sites": len(locs),
            "n_countries": len(countries),
        })
    token = data.get("nextPageToken")
    print(f"page {page + 1}: total {len(rows)} studies")
    if not token:
        break
    time.sleep(1)

with open("posts/2026-07-11-clinical-trial-duration/trials.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
print(f"wrote {len(rows)} rows")
