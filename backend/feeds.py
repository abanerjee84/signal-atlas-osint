"""Bounded RSS, RDF and Atom parsing; scripts and embedded images are never fetched."""

from defusedxml import ElementTree

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def parse_feed(payload: bytes) -> list[dict]:
    root = ElementTree.fromstring(payload)
    records = []
    for item in root.findall(".//item") + root.findall("{http://purl.org/rss/1.0/}item"):
        records.append({child.tag.split("}")[-1]: "".join(child.itertext()) for child in item})
    for entry in root.findall(ATOM + "entry"):
        record = {child.tag.split("}")[-1]: "".join(child.itertext()) for child in entry}
        record["link"] = next(
            (
                child.attrib.get("href", "")
                for child in entry
                if child.tag == ATOM + "link" and child.attrib.get("rel", "alternate") == "alternate"
            ),
            "",
        )
        record["author"] = entry.findtext(ATOM + "author/" + ATOM + "name", "")
        record["description"] = entry.findtext(MEDIA + "group/" + MEDIA + "description", "")
        record["community"] = next(
            (child.attrib.get("term", "") for child in entry if child.tag == ATOM + "category"), ""
        )
        records.append(record)
    return records
