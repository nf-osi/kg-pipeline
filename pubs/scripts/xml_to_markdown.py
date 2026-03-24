#!/usr/bin/env python3
"""Convert PMC JATS XML files to Markdown for selected publications.

Reads tools-portal-pmc-permissive-selected.tsv, parses each referenced XML file,
and writes a corresponding Markdown file to an output directory.
"""

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def get_text(el):
    """Recursively extract text from an XML element, handling inline markup."""
    if el is None:
        return ""
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        tag = child.tag
        inner = get_text(child)
        if tag in ("italic", "i"):
            parts.append(f"*{inner}*")
        elif tag in ("bold", "b"):
            parts.append(f"**{inner}**")
        elif tag == "sup":
            parts.append(f"^{inner}^")
        elif tag == "sub":
            parts.append(f"~{inner}~")
        elif tag == "xref":
            ref_type = child.get("ref-type", "")
            if ref_type == "bibr":
                parts.append(f"[{inner}]")
            elif ref_type == "fig":
                parts.append(f"(Figure {inner})")
            elif ref_type == "table":
                parts.append(f"(Table {inner})")
            else:
                parts.append(inner)
        elif tag == "ext-link":
            href = child.get("{http://www.w3.org/1999/xlink}href", "")
            parts.append(f"[{inner}]({href})" if href else inner)
        elif tag == "uri":
            href = child.get("{http://www.w3.org/1999/xlink}href", inner)
            parts.append(f"[{inner}]({href})")
        elif tag in ("email",):
            parts.append(inner)
        elif tag == "label":
            parts.append(inner + " ")
        elif tag in ("title",):
            # skip nested titles here; handled at section level
            pass
        else:
            parts.append(inner)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def extract_authors(front):
    """Extract author names from the front matter."""
    authors = []
    for contrib in front.iter("contrib"):
        if contrib.get("contrib-type") != "author":
            continue
        name_el = contrib.find("name")
        if name_el is not None:
            surname = name_el.findtext("surname", "")
            given = name_el.findtext("given-names", "")
            authors.append(f"{given} {surname}".strip())
    return authors


def extract_abstract(front):
    """Extract abstract text."""
    abstract_el = front.find(".//abstract")
    if abstract_el is None:
        return ""
    paragraphs = []
    for p in abstract_el.iter("p"):
        text = get_text(p).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def process_section(sec, level=2):
    """Recursively convert a <sec> element to Markdown."""
    lines = []
    title_el = sec.find("title")
    if title_el is not None:
        title_text = get_text(title_el).strip()
        if title_text:
            lines.append(f"{'#' * level} {title_text}")
            lines.append("")

    for child in sec:
        if child.tag == "title":
            continue
        elif child.tag == "p":
            text = get_text(child).strip()
            if text:
                lines.append(text)
                lines.append("")
        elif child.tag == "sec":
            lines.extend(process_section(child, level=min(level + 1, 6)))
        elif child.tag == "fig":
            caption = child.find("caption")
            if caption is not None:
                cap_text = get_text(caption).strip()
                lines.append(f"*Figure: {cap_text}*")
                lines.append("")
        elif child.tag == "table-wrap":
            caption = child.find("caption")
            if caption is not None:
                cap_text = get_text(caption).strip()
                lines.append(f"*Table: {cap_text}*")
                lines.append("")
        elif child.tag == "list":
            for item in child.findall("list-item"):
                item_text = get_text(item).strip()
                if item_text:
                    lines.append(f"- {item_text}")
            lines.append("")

    return lines


def extract_references(back):
    """Extract references from the back matter."""
    if back is None:
        return []
    refs = []
    for ref in back.iter("ref"):
        label = ref.findtext("label", "")
        citation = ref.find(".//element-citation")
        if citation is None:
            citation = ref.find(".//mixed-citation")
        if citation is None:
            continue

        # Authors
        authors = []
        for name_el in citation.findall(".//name"):
            surname = name_el.findtext("surname", "")
            given = name_el.findtext("given-names", "")
            authors.append(f"{given} {surname}".strip())
        author_str = ", ".join(authors)

        title = get_text(citation.find("article-title")).strip() if citation.find("article-title") is not None else ""
        source = citation.findtext("source", "")
        year = citation.findtext("year", "")
        volume = citation.findtext("volume", "")
        fpage = citation.findtext("fpage", "")
        lpage = citation.findtext("lpage", "")
        doi = ""
        for pub_id in citation.findall("pub-id"):
            if pub_id.get("pub-id-type") == "doi":
                doi = (pub_id.text or "").strip()

        parts = []
        if label:
            parts.append(f"{label}.")
        if author_str:
            parts.append(author_str + ".")
        if title:
            parts.append(title + ".")
        if source:
            parts.append(f"*{source}*.")
        if year:
            parts.append(year + ".")
        if volume:
            page_range = f"{fpage}-{lpage}" if fpage and lpage else fpage
            parts.append(f"{volume}:{page_range}." if page_range else f"{volume}.")
        if doi:
            parts.append(f"doi:{doi}")

        refs.append(" ".join(parts))
    return refs


def convert_xml_to_markdown(xml_path):
    """Convert a PMC JATS XML file to a Markdown string."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    front = root.find(".//front")
    body = root.find(".//body")
    back = root.find(".//back")

    # Metadata
    title = get_text(front.find(".//article-title")).strip() if front.find(".//article-title") is not None else ""
    journal = front.findtext(".//journal-title", "")
    authors = extract_authors(front)
    abstract = extract_abstract(front)

    # IDs
    pmcid = ""
    pmid = ""
    doi = ""
    for aid in front.iter("article-id"):
        id_type = aid.get("pub-id-type", "")
        if id_type == "pmcid":
            pmcid = (aid.text or "").strip()
        elif id_type == "pmid":
            pmid = (aid.text or "").strip()
        elif id_type == "doi":
            doi = (aid.text or "").strip()

    # Publication date
    pub_date = ""
    for pd in front.iter("pub-date"):
        year = pd.findtext("year", "")
        month = pd.findtext("month", "")
        day = pd.findtext("day", "")
        if year:
            parts = [year]
            if month:
                parts.insert(0, month.zfill(2))
            if day:
                parts.insert(0, day.zfill(2))
            pub_date = "-".join(reversed(parts)) if len(parts) > 1 else year
            break

    # Build markdown
    md = []
    md.append(f"# {title}")
    md.append("")
    if authors:
        md.append(f"**Authors:** {', '.join(authors)}")
        md.append("")
    if journal:
        md.append(f"**Journal:** {journal}")
        md.append("")
    if pub_date:
        md.append(f"**Published:** {pub_date}")
        md.append("")
    if pmcid:
        md.append(f"**PMCID:** {pmcid}")
    if pmid:
        md.append(f"**PMID:** {pmid}")
    if doi:
        md.append(f"**DOI:** {doi}")
    md.append("")

    if abstract:
        md.append("## Abstract")
        md.append("")
        md.append(abstract)
        md.append("")

    # Body sections
    if body is not None:
        for sec in body.findall("sec"):
            md.extend(process_section(sec, level=2))

    # References
    refs = extract_references(back)
    if refs:
        md.append("## References")
        md.append("")
        for ref in refs:
            md.append(f"- {ref}")
        md.append("")

    return "\n".join(md)


def main():
    base_dir = Path(__file__).resolve().parent.parent
    tsv_path = base_dir / "tools-portal-pmc-permissive-selected.tsv"
    output_dir = base_dir / "markdown_papers"
    output_dir.mkdir(exist_ok=True)

    # Read selected publications
    seen_pmcids = set()
    papers = []
    with open(tsv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            xml_file = row.get("xml_file", "").strip()
            pmcid = row.get("pmcid", "").strip()
            if not xml_file or pmcid in seen_pmcids:
                continue
            seen_pmcids.add(pmcid)
            papers.append((pmcid, base_dir / xml_file))

    print(f"Found {len(papers)} unique papers to convert")

    for pmcid, xml_path in papers:
        if not xml_path.exists():
            print(f"  SKIP {pmcid}: XML file not found at {xml_path}")
            continue
        try:
            md_content = convert_xml_to_markdown(xml_path)
            out_path = output_dir / f"{pmcid}.md"
            out_path.write_text(md_content, encoding="utf-8")
            print(f"  OK   {pmcid} -> {out_path.name}")
        except Exception as e:
            print(f"  ERR  {pmcid}: {e}")

    print(f"\nMarkdown files written to {output_dir}")


if __name__ == "__main__":
    main()
