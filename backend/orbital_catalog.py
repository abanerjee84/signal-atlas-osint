"""Public mission descriptions; catalogue membership is not operational status."""

import re

CATALOG = {
    "25544": ("ISS", "International Space Station"),
    "48274": ("Tiangong", "Crewed space station"),
    "20580": ("Hubble", "Space telescope"),
    "25994": ("Terra", "Earth observation"),
    "27424": ("Aqua", "Earth observation"),
    "31598": ("COSMO-SkyMed 1", "Radar Earth observation"),
    "39766": ("ALOS-2", "Radar Earth observation"),
    "43641": ("SAOCOM 1A", "Radar Earth observation"),
    "46265": ("SAOCOM 1B", "Radar Earth observation"),
    "57800": ("XRISM", "X-ray observatory"),
    "43700": ("QO-100", "Amateur radio communications"),
    "07530": ("AO-7", "Amateur radio satellite"),
    "39444": ("AO-73", "Educational satellite"),
    "44909": ("RS-44", "Amateur radio satellite"),
    "41603": ("LAPAN-A3", "Earth observation"),
}

DEFENCE_FR = "https://cnes.fr/dossiers/satellites-service-de-defense-de-nos-armees"
DEFENCE_US = "https://www.ssc.spaceforce.mil/Portals/3/SSC_Fact_Sheet_PNT_FINAL_1.pdf"
OBSERVER = "https://www.mmccants.org/tles/"
CURATED_OPERATORS = {
    "25544": (
        "INT",
        "NASA, Roscosmos, ESA, JAXA & CSA",
        "https://www.nasa.gov/reference/international-space-station/",
    ),
    "48274": ("CN", "China / China Manned Space Agency", "https://en.cmse.gov.cn/"),
    "20580": ("INT", "NASA & ESA", "https://science.nasa.gov/mission/hubble/"),
    "25994": ("US", "United States / NASA", "https://terra.nasa.gov/"),
    "27424": ("US", "United States / NASA", "https://aqua.nasa.gov/"),
    "31598": ("IT", "Italy / ASI & Defence", "https://www.asi.it/en/earth-science/cosmo-skymed/"),
    "39766": ("JP", "Japan / JAXA", "https://global.jaxa.jp/projects/sat/alos2/"),
    "43641": (
        "AR",
        "Argentina / CONAE",
        "https://www.argentina.gob.ar/ciencia/conae/misiones-espaciales/saocom",
    ),
    "46265": (
        "AR",
        "Argentina / CONAE",
        "https://www.argentina.gob.ar/ciencia/conae/misiones-espaciales/saocom",
    ),
    "57800": ("JP", "Japan / JAXA (NASA & ESA collaboration)", "https://www.xrism.jaxa.jp/en/"),
    "43700": (
        "QA",
        "Qatar / Es'hailSat (AMSAT-DL payload)",
        "https://amsat-dl.org/en/eshail-2-amsat-phase-4-a/",
    ),
    "07530": ("INT", "AMSAT international collaboration", "https://www.amsat.org/two-way-satellites/ao-7/"),
    "39444": ("GB", "United Kingdom / AMSAT-UK & AMSAT-NL", "https://amsat-uk.org/funcube/funcube-1/"),
    "44909": ("RU", "Russia / DOSAAF", "https://www.amsat.org/two-way-satellites/rs-44/"),
    "41603": ("ID", "Indonesia / LAPAN", "https://www.brin.go.id/"),
}
# Anchored families prevent, for example, a rocket body named after a payload
# or an unrelated commercial satellite becoming a military spacecraft.
FAMILIES = [
    (
        r"PRAETORIAN SDA[_ ]\d+",
        "Proliferated military communications",
        "United States / Space Development Agency",
        "US",
        "https://www.sda.mil/home/about-us/faq/",
    ),
    (
        r"VICTUS HAZE PUMA",
        "Responsive-space demonstration",
        "United States / Space Force",
        "US",
        "https://rocketlabcorp.com/missions/launches/victus-haze/",
    ),
    (
        r"SAR[- ]?LUPE \d+|SARAH \d+",
        "Radar reconnaissance",
        "Germany / Bundeswehr",
        "DE",
        "https://www.bundeswehr.de/de/organisation/cyber-und-informationsraum/aktuelles/sarah-ein-enormer-gewinn-fuer-die-aufklaerung-5442966",
    ),
    (r"CERES \d+", "Signals intelligence", "France / Defence & CNES", "FR", "https://cnes.fr/projets/ceres"),
    (r"CSO \d+|HELIOS 2[AB]", "Optical reconnaissance", "France / Defence & CNES", "FR", DEFENCE_FR),
    (
        r"SKYNET \d+[A-Z]",
        "Military communications",
        "United Kingdom / Ministry of Defence",
        "GB",
        "https://www.gov.uk/guidance/skynet-6",
    ),
    (r"SYRACUSE \d+[A-Z]", "Military communications", "France / Defence", "FR", DEFENCE_FR),
    (
        r"WGS (?:F?\d+)(?: \(USA \d+\))?|AEHF-\d+(?: \(USA \d+\))?|MUOS-\d+|USA \d+ \(MILSTAR-[\d ]+\)",
        "Military communications",
        "United States / Defence",
        "US",
        DEFENCE_US,
    ),
    (
        r"GSAT[- ]7(?:A|R)?|CMS-03 \(GSAT-7R\)",
        "Military communications",
        "India / Defence & ISRO",
        "IN",
        "https://www.isro.gov.in/GSAT_7.html",
    ),
    (
        r"NOSS \d+-\d+ \([A-Z]\)|FIA RADAR \d+",
        "Observer-identified reconnaissance",
        "United States (observer identification)",
        "US",
        OBSERVER,
    ),
    (
        r"IGS (?:\d+[A-Z]?|RADAR \d+|OPT(?:ICAL)? \d+)",
        "Information gathering",
        "Japan (observer identification)",
        "JP",
        OBSERVER,
    ),
    (r"STSS DEMO \d+", "Missile-tracking demonstration", "United States / Defence", "US", OBSERVER),
    (
        r"SAPPHIRE",
        "Space surveillance",
        "Canada / Department of National Defence",
        "CA",
        "https://www.canada.ca/en/air-force/corporate/space/capabilities.html",
    ),
]
FAMILIES = [
    (re.compile(pattern, re.I), purpose, operator, country, url)
    for pattern, purpose, operator, country, url in FAMILIES
]


def mission_metadata(number, name, source):
    name = " ".join(name.split())
    if re.search(r"\b(?:R/B|RK|DEB|COVER)\b|\s[rR]$", name):
        return None
    for pattern, purpose, operator, country, url in FAMILIES:
        if pattern.fullmatch(name):
            return {
                "name": name,
                "purpose": purpose,
                "role": "military",
                "operator": operator,
                "operator_country": country,
                "mission_url": url,
                "mission_basis": "Observer identification"
                if url == OBSERVER
                else "Public mission description",
            }
    if number in CATALOG:
        label, purpose = CATALOG[number]
        country, operator, url = CURATED_OPERATORS[number]
        return {
            "name": label,
            "purpose": purpose,
            "role": "station" if number in {"25544", "48274"} else "civil",
            "operator": operator,
            "operator_country": country,
            "mission_url": url,
            "mission_basis": "Curated public catalogue",
        }
    if source == "CelesTrak Military" and name:
        return {
            "name": name,
            "purpose": "Military spacecraft; mission details unspecified",
            "role": "military",
            "operator": "Not specified",
            "mission_basis": "CelesTrak military catalogue",
        }
    if source == "CelesTrak GPS" and re.fullmatch(r"GPS B.+", name):
        return {
            "name": name,
            "purpose": "Civil and military navigation",
            "role": "navigation",
            "operator": "United States / Space Force",
            "operator_country": "US",
            "mission_url": "https://www.gps.gov/systems/gps/index.php",
            "mission_basis": "Public mission description (dual use)",
        }
    return None
