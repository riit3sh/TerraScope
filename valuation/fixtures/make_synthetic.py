"""Generate the SYNTHETIC land-price fixture used by tests and demo mode.

These rows are invented. They exist so the import/training/serving path can be
exercised without a real dataset, and every row is stamped ``SYNTHETIC_FIXTURE``
in its source column so nothing downstream can mistake them for market evidence.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path


OUTPUT = Path(__file__).with_name("synthetic_land_prices.csv")

# Real district names and plausible centroids, so the support check is exercised
# over realistic geography. The PRICES ARE INVENTED.
DISTRICTS = [
    # Maharashtra
    ("Pune", "Maharashtra", 18.5204, 73.8567, 6200.0),
    ("Mumbai Suburban", "Maharashtra", 19.1136, 72.8697, 24000.0),
    ("Thane", "Maharashtra", 19.2183, 72.9781, 14500.0),
    ("Nashik", "Maharashtra", 19.9975, 73.7898, 3100.0),
    ("Nagpur", "Maharashtra", 21.1458, 79.0882, 2700.0),
    ("Aurangabad", "Maharashtra", 19.8762, 75.3433, 2400.0),
    # Tamil Nadu
    ("Chennai", "Tamil Nadu", 13.0827, 80.2707, 11500.0),
    ("Coimbatore", "Tamil Nadu", 11.0168, 76.9558, 3800.0),
    ("Vellore", "Tamil Nadu", 12.9165, 79.1325, 1900.0),
    ("Madurai", "Tamil Nadu", 9.9252, 78.1198, 2200.0),
    ("Salem", "Tamil Nadu", 11.6643, 78.1460, 1800.0),
    ("Tiruchirappalli", "Tamil Nadu", 10.7905, 78.7047, 2000.0),
    # Karnataka
    ("Bengaluru Urban", "Karnataka", 12.9716, 77.5946, 9800.0),
    ("Mysuru", "Karnataka", 12.2958, 76.6394, 3200.0),
    ("Mangaluru", "Karnataka", 12.9141, 74.8560, 4200.0),
    ("Hubballi", "Karnataka", 15.3647, 75.1240, 2100.0),
    # Telangana / Andhra Pradesh
    ("Hyderabad", "Telangana", 17.3850, 78.4867, 8600.0),
    ("Warangal", "Telangana", 17.9689, 79.5941, 1900.0),
    ("Visakhapatnam", "Andhra Pradesh", 17.6868, 83.2185, 4600.0),
    ("Vijayawada", "Andhra Pradesh", 16.5062, 80.6480, 3900.0),
    ("YSR Kadapa", "Andhra Pradesh", 14.4674, 78.8242, 1500.0),
    ("Tirupati", "Andhra Pradesh", 13.6288, 79.4192, 2600.0),
    # Kerala
    ("Ernakulam", "Kerala", 9.9312, 76.2673, 5400.0),
    ("Thiruvananthapuram", "Kerala", 8.5241, 76.9366, 4100.0),
    ("Kozhikode", "Kerala", 11.2588, 75.7804, 3600.0),
    # North / West / East
    ("New Delhi", "Delhi", 28.6139, 77.2090, 19000.0),
    ("Gurugram", "Haryana", 28.4595, 77.0266, 12000.0),
    ("Noida", "Uttar Pradesh", 28.5355, 77.3910, 8200.0),
    ("Lucknow", "Uttar Pradesh", 26.8467, 80.9462, 3400.0),
    ("Jaipur", "Rajasthan", 26.9124, 75.7873, 3700.0),
    ("Ahmedabad", "Gujarat", 23.0225, 72.5714, 5200.0),
    ("Surat", "Gujarat", 21.1702, 72.8311, 4300.0),
    ("Indore", "Madhya Pradesh", 22.7196, 75.8577, 3300.0),
    ("Bhopal", "Madhya Pradesh", 23.2599, 77.4126, 2800.0),
    ("Kolkata", "West Bengal", 22.5726, 88.3639, 7400.0),
    ("Patna", "Bihar", 25.5941, 85.1376, 3000.0),
    ("Bhubaneswar", "Odisha", 20.2961, 85.8245, 3100.0),
    ("Chandigarh", "Chandigarh", 30.7333, 76.7794, 7800.0),
    ("Dehradun", "Uttarakhand", 30.3165, 78.0322, 3500.0),
    ("Guwahati", "Assam", 26.1445, 91.7362, 2900.0),
]

LAND_USE_MULTIPLIER = {
    "residential": 1.0,
    "commercial": 1.65,
    "industrial": 0.78,
    "agricultural": 0.22,
    "mixed_use": 1.25,
}


def build(rows_per_district: int = 30, seed: int = 20260926) -> list[dict[str, object]]:
    rng = random.Random(seed)
    start = date(2021, 1, 1)
    records: list[dict[str, object]] = []
    counter = 0
    for name, state, latitude, longitude, base_price in DISTRICTS:
        for _ in range(rows_per_district):
            counter += 1
            land_use = rng.choices(
                list(LAND_USE_MULTIPLIER), weights=[0.5, 0.18, 0.1, 0.12, 0.1]
            )[0]
            offset_days = rng.randint(0, 365 * 4)
            observed = start + timedelta(days=offset_days)
            # Invented drift and noise; not calibrated to any real market.
            drift = 1.0 + 0.055 * (offset_days / 365.0)
            jitter = rng.uniform(0.82, 1.18)
            price_per_sqft = base_price * LAND_USE_MULTIPLIER[land_use] * drift * jitter
            area_sqft = rng.choice([1200, 1800, 2400, 3600, 5400, 8000, 10890])
            basis = "transaction" if rng.random() < 0.7 else "asking"
            if basis == "asking":
                price_per_sqft *= 1.06  # asking prices sit above completed deals
            records.append(
                {
                    "record_id": f"SYN-{counter:05d}",
                    "latitude": round(latitude + rng.uniform(-0.09, 0.09), 6),
                    "longitude": round(longitude + rng.uniform(-0.09, 0.09), 6),
                    "district": name,
                    "state": state,
                    "area_value": area_sqft,
                    "area_unit": "sqft",
                    "land_use": land_use,
                    "observation_date": observed.isoformat(),
                    "price_value": round(price_per_sqft * area_sqft, 2),
                    "price_unit": "total_inr",
                    "price_basis": basis,
                    "source": "SYNTHETIC_FIXTURE",
                }
            )
    return records


def main() -> None:
    records = build()
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(f"wrote {len(records)} SYNTHETIC rows to {OUTPUT}")


if __name__ == "__main__":
    main()
