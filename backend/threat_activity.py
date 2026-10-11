"""Conservative reported attribution. Never infer actor nationality from an IP or catalog alias."""

import re

from .attack_vectors import extract_vectors
from .geo import country_matchers, mentioned_countries
from .models import ThreatMetadata

INCIDENT = re.compile(
    r"\b(?:cyberattacks?|cyber[- ]attacks?|ransomware|hackers?|hacking|hacked|breach(?:es|ed)?|"
    r"espionage|malware|botnet|backdoor|DDoS|phishing|vishing|ClickFix|intrusion|extortion|exploitation|exploit(?:ed|ing)|APT\d+|UAT-\d{4,6}|UNC\d{3,6}|threat actors?)\b",
    re.I,
)
ACTORS = re.compile(
    r"\b(?:APT\s?\d{1,3}|Lazarus(?: Group)?|ShinyHunters|Qilin|LockBit|Akira|"
    r"Sandworm|Scattered Spider|Salt Typhoon|Volt Typhoon|Flax Typhoon|"
    r"Fancy Bear|Cozy Bear|Kimsuky|Turla|MuddyWater|TA\d{3,4}|"
    r"OilRig|Gamaredon|FIN\d+|BlackCat|ALPHV|Cl0p|UAT-\d{4,6}|UAC-\d{4,6})\b",
    re.I,
)
ROLE = r"(?:hackers?|threat actors?|attackers?|operators?|APT(?:\s?\d{1,3})?|UAT-\d{4,6}|UAC-\d{4,6}|cybercriminals?|espionage group|hacking group|threat group)"


def extract_threat(text):
    text = re.sub(r"\s+", " ", text.replace("–", "-").replace("‑", "-")).strip()[:10000]
    if not INCIDENT.search(text):
        return None
    attacker, evidence = {}, []
    matchers = list(country_matchers()) + [
        ("KP", re.compile(r"\bNorth[- ]Korean\b", re.I)),
        ("KR", re.compile(r"\bSouth[- ]Korean\b", re.I)),
    ]
    for code, matcher in matchers:
        for match in matcher.finditer(text):
            prefix = text[max(0, match.start() - 55) : match.start()]
            suffix = text[match.end() : match.end() + 95]
            if re.search(r"\b(?:not|no evidence|unrelated|denied|denies)\b", prefix, re.I):
                continue
            if re.match(
                r"(?:[- ](?:linked|backed|aligned|based|nexus|sponsored|supported))?"
                r"(?:[- ](?:state|government|cyber|advanced|persistent|sponsored|backed|linked)){0,4}\s+"
                + ROLE
                + r"\b",
                suffix,
                re.I,
            ):
                attacker[code] = text[match.start() : match.end() + min(90, len(suffix))]
    # More than one attribution country is ambiguous. Preserve text but draw no origin edge.
    attacker_country = next(iter(attacker)) if len(attacker) == 1 else None
    evidence = list(attacker.values())
    victims, victim_evidence = set(), []
    for match in re.finditer(
        r"\b(?:target(?:s|ed|ing)?|attack(?:s|ed|ing)?|breach(?:es|ed)?|hacked|"
        r"hit|compromis(?:ed|es|ing)|affected)\s+(?:against\s+|on\s+|in\s+)?([^.!?;]{1,150})"
        r"|\b(?:cyberattacks?|ransomware|breach|(?:espionage|phishing|malware|ransomware) campaign)\s+(?:against|on|in)\s+([^.!?;]{1,150})",
        text,
        re.I,
    ):
        before = text[max(0, match.start() - 30) : match.start()]
        if re.search(r"\b(?:not|never|no evidence)\b", before, re.I):
            continue
        clause = re.split(
            r"\b(?:by|while|whereas|using|linked to|backed by|according to|reported by|said|says)\b",
            match.group(1) or match.group(2),
            maxsplit=1,
            flags=re.I,
        )[0]
        codes = mentioned_countries(clause)
        if codes:
            victims.update(codes)
            victim_evidence.append(match.group(0)[:250])
    name = ACTORS.search(text)
    vectors, vector_evidence = extract_vectors(text)
    kind = next(
        (
            label
            for pattern, label in [
                (r"ransomware|extortion", "Ransomware / extortion"),
                (r"DDoS", "DDoS"),
                (r"espionage", "Cyber espionage"),
                (r"breach|stolen|leaked", "Data breach"),
                (r"phishing", "Phishing"),
                (r"malware|botnet", "Malware / botnet"),
            ]
            if re.search(pattern, text, re.I)
        ),
        "Reported cyber activity",
    )
    return ThreatMetadata(
        actor=name.group(0) if name else "Unknown actor",
        attacker_country=attacker_country,
        victim_countries=sorted(victims)[:20],
        attack_kind=kind,
        attack_vectors=vectors,
        vector_evidence=vector_evidence,
        cves=sorted(set(re.findall(r"\bCVE-\d{4}-\d{4,8}\b", text, re.I)))[:20],
        attribution_basis=("Source text reports country attribution: " + " | ".join(evidence))[:1000]
        if attacker_country
        else "Attacker country unknown or ambiguous; actor names and infrastructure do not establish nationality",
        victim_basis=("Source text describes targeting: " + " | ".join(victim_evidence))[:1000]
        if victims
        else "No explicitly named victim country in a targeting clause",
    )
