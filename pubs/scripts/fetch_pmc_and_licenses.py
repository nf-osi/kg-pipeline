#!/usr/bin/env python3
"""
Comprehensive script to fetch PMC IDs, license information, and full-text XML.

This script:
1. Reads all publications from tools-portal-pubs.tsv
2. Fetches PMC IDs using NCBI E-utilities
3. Fetches and parses license information from PMC metadata (or cached XML)
4. Downloads full-text XML files for each PMC article
5. Verifies full-text availability (not just abstract)
6. Outputs a complete table with PMC IDs and license details

Usage:
    python3 fetch_pmc_and_licenses.py [--no-cache]

    --no-cache: Force re-fetching from NCBI even if cached XML exists (default: use cache)

Output:
    tools-portal-pmc-with-licenses.tsv
    pmc_fulltext_xml/  (directory with XML files)
"""

import csv
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
import os
import sys

def extract_pmid(pmid_str):
    """Extract numeric PMID from various formats (e.g., 'PMID:12345' -> '12345')"""
    if not pmid_str:
        return None
    match = re.search(r'\d+', pmid_str)
    return match.group(0) if match else None

def extract_pmc_number(pmcid):
    """Extract numeric part from PMC ID (e.g., 'PMC12345' -> '12345')"""
    if not pmcid:
        return None
    match = re.search(r'\d+', pmcid)
    return match.group(0) if match else None

def parse_license_from_text(text):
    """
    Parse license type from text - comprehensive and careful parsing.
    Returns (license_type, confidence)
    """
    if not text:
        return None, 'none'

    text_lower = text.lower()

    # Check for boilerplate statements (not actual licenses)
    if 'reprints and permissions' in text_lower and 'online' in text_lower:
        return None, 'boilerplate'

    # Check if text contains a CC URL (even if embedded in text)
    if 'creativecommons.org/licenses' in text_lower or 'creativecommons.org/publicdomain' in text_lower:
        if 'creativecommons.org/licenses/by/4.0' in text_lower:
            return 'CC-BY-4.0', 'url'
        elif 'creativecommons.org/licenses/by-nc-nd/' in text_lower:
            return 'CC-BY-NC-ND', 'url'
        elif 'creativecommons.org/licenses/by-nc-sa/' in text_lower:
            return 'CC-BY-NC-SA', 'url'
        elif 'creativecommons.org/licenses/by-nc/' in text_lower:
            return 'CC-BY-NC', 'url'
        elif 'creativecommons.org/licenses/by-sa/' in text_lower:
            return 'CC-BY-SA', 'url'
        elif 'creativecommons.org/licenses/by/' in text_lower and '/nc' not in text_lower:
            return 'CC-BY', 'url'
        elif 'creativecommons.org/publicdomain' in text_lower:
            return 'Public Domain', 'url'

    # Parse from text - order matters! Check most restrictive first

    # Check for fair use statement (manuscripts with text mining + fair use language)
    if 'text mining' in text_lower and 'fair use' in text_lower:
        return 'Fair use (license unspecified)', 'text'

    # Check for public domain
    if 'public domain' in text_lower:
        return 'Public Domain', 'text'

    # Check for CC licenses - most specific first
    if any(phrase in text_lower for phrase in ['cc by-nc-nd', 'cc-by-nc-nd', 'by-nc-nd',
                                                'noncommercial-noderivs', 'non-commercial and no modifications',
                                                'noncommercial and no modifications']):
        return 'CC-BY-NC-ND', 'text'

    if any(phrase in text_lower for phrase in ['cc by-nc-sa', 'cc-by-nc-sa', 'by-nc-sa',
                                                'noncommercial-sharealike']):
        return 'CC-BY-NC-SA', 'text'

    if any(phrase in text_lower for phrase in ['cc by-nc', 'cc-by-nc', 'by-nc',
                                                'non-commercial', 'noncommercial']):
        # Make sure it's not ND or SA
        if 'no deriv' not in text_lower and 'noderivs' not in text_lower and 'no modif' not in text_lower:
            return 'CC-BY-NC', 'text'

    if any(phrase in text_lower for phrase in ['cc by-sa', 'cc-by-sa', 'by-sa', 'sharealike']):
        return 'CC-BY-SA', 'text'

    if any(phrase in text_lower for phrase in ['cc by 4.0', 'cc-by 4.0', 'attribution 4.0']):
        # Make sure no restrictions
        if 'non-commercial' not in text_lower and 'noderivs' not in text_lower:
            return 'CC-BY-4.0', 'text'

    if any(phrase in text_lower for phrase in ['cc by', 'cc-by', 'creative commons attribution']):
        # Make sure no restrictions
        if 'non-commercial' not in text_lower and 'noderivs' not in text_lower and 'no deriv' not in text_lower:
            return 'CC-BY', 'text'

    # Not a recognizable CC license
    return None, 'unrecognized'

def extract_license_from_cached_xml(xml_file):
    """Extract license URL or text from cached XML file"""
    if not os.path.exists(xml_file):
        return None, None

    try:
        tree = ET.parse(xml_file)
        article = tree.getroot()

        # Look for license element
        license_elem = article.find('.//license')
        if license_elem is None:
            return None, None

        # Check for URL in href attribute
        license_url = license_elem.get('{http://www.w3.org/1999/xlink}href', '')
        if license_url:
            return license_url, license_url

        # If no URL, get the license text
        license_p = license_elem.find('.//license-p')
        if license_p is not None:
            # Get all text content, clean up whitespace
            license_text = ''.join(license_p.itertext()).strip()
            # Collapse multiple spaces/newlines
            license_text = ' '.join(license_text.split())
            return license_text, license_text

        return None, None
    except Exception as e:
        return None, None

def fetch_pmc_ids_batch(pmids):
    """
    Fetch PMC IDs for a batch of PMIDs using NCBI E-utilities.
    Returns dict mapping PMID -> PMC ID.
    """
    if not pmids:
        return {}

    # Remove duplicates and None values
    pmids = list(set([p for p in pmids if p]))
    if not pmids:
        return {}

    pmid_to_pmc = {}
    batch_size = 200  # NCBI recommends batches of 200

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i+batch_size]
        pmid_str = ','.join(batch)

        url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid_str}&retmode=xml'

        try:
            print(f"  Fetching PMC IDs for PMIDs {i+1}-{min(i+batch_size, len(pmids))} of {len(pmids)}...")
            with urllib.request.urlopen(url, timeout=30) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)

            for article in root.findall('.//PubmedArticle'):
                # Get PMID
                pmid_elem = article.find('.//PMID')
                if pmid_elem is not None:
                    pmid = pmid_elem.text

                    # Look for PMC ID in PubmedData/ArticleIdList (not in references)
                    pubmed_data = article.find('.//PubmedData')
                    if pubmed_data is not None:
                        # Find ArticleId with IdType="pmc" in the article's own metadata
                        for article_id in pubmed_data.findall('.//ArticleId'):
                            if article_id.get('IdType') == 'pmc':
                                pmc_id = article_id.text
                                # Ensure PMC ID has proper format (PMC prefix)
                                if not pmc_id.startswith('PMC'):
                                    pmc_id = 'PMC' + pmc_id
                                pmid_to_pmc[pmid] = pmc_id
                                break

            # Rate limit: max 3 requests per second
            time.sleep(0.34)

        except Exception as e:
            print(f"    Warning: Error fetching batch starting at {i}: {e}")
            continue

    return pmid_to_pmc

def fetch_pmc_license_metadata_batch(pmcids):
    """
    Fetch license and access metadata for a batch of PMC IDs.
    Returns dict mapping PMC ID -> metadata dict.
    """
    if not pmcids:
        return {}

    pmcid_to_info = {}
    batch_size = 100

    for i in range(0, len(pmcids), batch_size):
        batch = pmcids[i:i+batch_size]
        batch_numbers = [extract_pmc_number(pmc) for pmc in batch if extract_pmc_number(pmc)]

        if not batch_numbers:
            continue

        id_str = ','.join(batch_numbers)
        url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={id_str}&retmode=xml'

        try:
            print(f"  Fetching licenses for PMC articles {i+1}-{min(i+batch_size, len(pmcids))} of {len(pmcids)}...")
            with urllib.request.urlopen(url, timeout=60) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)

            # Process each article
            for article in root.findall('.//article'):
                # Get PMC ID
                pmc_id = None
                for article_id in article.findall('.//article-id'):
                    if article_id.get('pub-id-type') == 'pmcid':
                        pmc_id = article_id.text
                        break

                if not pmc_id:
                    continue

                article_info = {
                    'is_open_access': False,
                    'is_manuscript': False,
                    'license_type': None,
                    'license_url_or_text': None,
                    'collection': None
                }

                # Parse custom metadata for access flags
                for custom_meta in article.findall('.//custom-meta'):
                    meta_name_elem = custom_meta.find('meta-name')
                    meta_value_elem = custom_meta.find('meta-value')

                    if meta_name_elem is not None and meta_value_elem is not None:
                        meta_name = meta_name_elem.text
                        meta_value = meta_value_elem.text

                        if meta_name == 'pmc-prop-open-access' and meta_value == 'yes':
                            article_info['is_open_access'] = True
                        elif meta_name == 'pmc-prop-manuscript' and meta_value == 'yes':
                            article_info['is_manuscript'] = True
                        elif meta_name == 'pmc-collection-title':
                            article_info['collection'] = meta_value

                # Parse license information from <license> element
                license_elem = article.find('.//license')
                if license_elem is not None:
                    # Check for URL in href attribute
                    license_url = license_elem.get('{http://www.w3.org/1999/xlink}href', '')

                    # Get license text from <license-p>
                    license_text = None
                    license_p = license_elem.find('.//license-p')
                    if license_p is not None:
                        license_text = ''.join(license_p.itertext()).strip()
                        # Collapse multiple spaces/newlines
                        license_text = ' '.join(license_text.split())

                    # Store URL or text (prefer URL if available, otherwise text)
                    if license_url:
                        article_info['license_url_or_text'] = license_url
                    elif license_text:
                        article_info['license_url_or_text'] = license_text

                    # Parse license type - try URL first, then text
                    if license_url:
                        parsed_license, confidence = parse_license_from_text(license_url)
                        if parsed_license:
                            article_info['license_type'] = parsed_license

                    if not article_info['license_type'] and license_text:
                        parsed_license, confidence = parse_license_from_text(license_text)
                        if parsed_license:
                            article_info['license_type'] = parsed_license

                pmcid_to_info[pmc_id] = article_info

            # Rate limit
            time.sleep(0.34)

        except Exception as e:
            print(f"    Warning: Error fetching batch: {e}")
            continue

    return pmcid_to_info

def determine_license_category(info):
    """Determine the final license category from parsed metadata"""
    if info['license_type']:
        return info['license_type']
    elif info['is_open_access']:
        return 'Open Access (license unspecified)'
    elif info['is_manuscript']:
        return 'NIH Public Access/Author Manuscripts'
    else:
        return 'PMC (access type unspecified)'

def check_fulltext_availability(article_xml):
    """
    Check if XML contains full-text content (body sections).
    Returns True if full-text is available, False if only abstract/metadata.
    """
    try:
        # Look for body element which contains full text
        body = article_xml.find('.//body')
        if body is not None:
            # Check if body has substantial content (not just empty tags)
            body_text = ''.join(body.itertext()).strip()
            if len(body_text) > 100:  # Arbitrary threshold
                return True

        # Some articles might have sections instead of body
        sections = article_xml.findall('.//sec')
        if sections and len(sections) > 0:
            total_text = sum(len(''.join(sec.itertext()).strip()) for sec in sections)
            if total_text > 100:
                return True

        return False
    except:
        return False

def download_pmc_xml_files(pmcid_to_info, output_dir='pmc_fulltext_xml', use_cache=True):
    """
    Download full-text XML files for PMC articles and verify full-text availability.
    If use_cache=True, skip downloading files that already exist.
    Returns dict mapping PMC ID -> {'has_fulltext': bool, 'xml_file': str}
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"  Created directory: {output_dir}/")

    pmcid_fulltext_status = {}
    pmcids = list(pmcid_to_info.keys())

    # If using cache, check which files already exist
    pmcids_to_download = []
    if use_cache:
        for pmc_id in pmcids:
            xml_filename = os.path.join(output_dir, f'{pmc_id}.xml')
            if os.path.exists(xml_filename):
                # Use cached file
                try:
                    tree = ET.parse(xml_filename)
                    article = tree.getroot()
                    has_fulltext = check_fulltext_availability(article)
                    pmcid_fulltext_status[pmc_id] = {
                        'has_fulltext': has_fulltext,
                        'xml_file': xml_filename
                    }
                except:
                    # If file is corrupted, re-download
                    pmcids_to_download.append(pmc_id)
            else:
                pmcids_to_download.append(pmc_id)

        if pmcids_to_download:
            print(f"  Using {len(pmcid_fulltext_status)} cached XML files")
            print(f"  Downloading {len(pmcids_to_download)} missing XML files...")
        else:
            print(f"  Using all {len(pmcid_fulltext_status)} cached XML files (no downloads needed)")
            return pmcid_fulltext_status
    else:
        pmcids_to_download = pmcids

    # Download missing or all files (depending on cache setting)
    batch_size = 50  # Smaller batches for XML download
    for i in range(0, len(pmcids_to_download), batch_size):
        batch = pmcids_to_download[i:i+batch_size]
        batch_numbers = [extract_pmc_number(pmc) for pmc in batch if extract_pmc_number(pmc)]

        if not batch_numbers:
            continue

        id_str = ','.join(batch_numbers)
        url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={id_str}&retmode=xml'

        try:
            print(f"    Downloading XML {i+1}-{min(i+batch_size, len(pmcids_to_download))} of {len(pmcids_to_download)}...")
            with urllib.request.urlopen(url, timeout=60) as response:
                xml_data = response.read()

            # Parse the batch XML
            root = ET.fromstring(xml_data)

            # Process each article in the batch
            for article in root.findall('.//article'):
                # Get PMC ID
                pmc_id = None
                for article_id in article.findall('.//article-id'):
                    if article_id.get('pub-id-type') == 'pmcid':
                        pmc_id = article_id.text
                        break

                if not pmc_id:
                    continue

                # Save individual XML file
                pmc_num = extract_pmc_number(pmc_id)
                xml_filename = os.path.join(output_dir, f'{pmc_id}.xml')

                # Convert article element back to XML string
                article_xml_str = ET.tostring(article, encoding='unicode')
                with open(xml_filename, 'w', encoding='utf-8') as f:
                    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                    f.write(article_xml_str)

                # Check if full-text is available
                has_fulltext = check_fulltext_availability(article)

                pmcid_fulltext_status[pmc_id] = {
                    'has_fulltext': has_fulltext,
                    'xml_file': xml_filename
                }

            time.sleep(0.34)  # Rate limit

        except Exception as e:
            print(f"    Warning: Error downloading batch: {e}")
            continue

    return pmcid_fulltext_status

def normalize_doi(doi):
    """Normalize DOI for comparison"""
    if not doi:
        return None
    # Remove URL prefix
    doi = re.sub(r'^https?://(www\.)?doi\.org/', '', doi)
    doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
    return doi.strip().lower()

def main():
    input_file = 'tools-portal-pubs.tsv'
    main_portal_file = 'main-portal-pubs.tsv'
    output_file = 'subsets/tools-portal-pmc-with-licenses.tsv'
    xml_cache_dir = 'pmc_fulltext_xml'

    # Parse command line arguments
    use_cache = True
    if '--no-cache' in sys.argv:
        use_cache = False
        print("Note: --no-cache specified, will fetch all data from NCBI")
        print()

    # Step 1: Read all publications
    print("="*80)
    print("PMC ID and License Fetcher")
    print("="*80)
    print()
    print(f"Reading {input_file}...")

    all_records = []
    pmid_to_record = {}

    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            all_records.append(row)
            pmid = extract_pmid(row.get('pmid', ''))
            if pmid:
                pmid_to_record[pmid] = row

    print(f"  Total records: {len(all_records)}")
    print(f"  Records with PMID: {len(pmid_to_record)}")
    print()

    # Step 1.5: Read main-portal publications for cross-checking
    print(f"Reading {main_portal_file} for cross-checking...")

    main_portal_dois = set()
    main_portal_pmids = set()

    try:
        with open(main_portal_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                doi = normalize_doi(row.get('doi', ''))
                if doi:
                    main_portal_dois.add(doi)
                pmid = extract_pmid(row.get('pmid', ''))
                if pmid:
                    main_portal_pmids.add(pmid)

        print(f"  Main-portal records: {len(main_portal_dois)} DOIs, {len(main_portal_pmids)} PMIDs")
        print()
    except FileNotFoundError:
        print(f"  Warning: {main_portal_file} not found - skipping cross-check")
        print()
        main_portal_dois = set()
        main_portal_pmids = set()

    # Step 2: Get PMC IDs (from cache or NCBI)
    pmid_to_pmc = {}

    if use_cache and os.path.exists(output_file):
        print("Step 1: Reading PMC IDs from existing output file...")
        print()

        # Read PMC IDs from existing TSV
        with open(output_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                pmid = extract_pmid(row.get('pmid', ''))
                pmcid = row.get('pmcid', '')
                if pmid and pmcid:
                    pmid_to_pmc[pmid] = pmcid

        print(f"  ✓ PMC IDs loaded from cache: {len(pmid_to_pmc)}")
        print()
    else:
        print("Step 1: Fetching PMC IDs from NCBI...")
        print()

        pmids = list(pmid_to_record.keys())
        pmid_to_pmc = fetch_pmc_ids_batch(pmids)

        print()
        print(f"  ✓ PMC IDs found: {len(pmid_to_pmc)} out of {len(pmids)} ({len(pmid_to_pmc)*100/len(pmids):.1f}%)")
        print()

    # Step 3: Fetch license metadata
    pmcids = list(pmid_to_pmc.values())
    pmcid_to_info = {}

    if use_cache and os.path.exists(xml_cache_dir):
        print("Step 2: Extracting license information from cached XML files...")
        print()

        # Try to extract from cache first
        for pmc_id in pmcids:
            xml_file = os.path.join(xml_cache_dir, f'{pmc_id}.xml')
            if os.path.exists(xml_file):
                license_url_or_text, _ = extract_license_from_cached_xml(xml_file)

                # Parse the license
                license_type = None
                if license_url_or_text:
                    parsed_license, confidence = parse_license_from_text(license_url_or_text)
                    if parsed_license:
                        license_type = parsed_license

                # Get basic metadata from XML
                try:
                    tree = ET.parse(xml_file)
                    article = tree.getroot()

                    is_open_access = False
                    is_manuscript = False
                    collection = None

                    for custom_meta in article.findall('.//custom-meta'):
                        meta_name_elem = custom_meta.find('meta-name')
                        meta_value_elem = custom_meta.find('meta-value')
                        if meta_name_elem is not None and meta_value_elem is not None:
                            meta_name = meta_name_elem.text
                            meta_value = meta_value_elem.text
                            if meta_name == 'pmc-prop-open-access' and meta_value == 'yes':
                                is_open_access = True
                            elif meta_name == 'pmc-prop-manuscript' and meta_value == 'yes':
                                is_manuscript = True
                            elif meta_name == 'pmc-collection-title':
                                collection = meta_value

                    pmcid_to_info[pmc_id] = {
                        'is_open_access': is_open_access,
                        'is_manuscript': is_manuscript,
                        'license_type': license_type,
                        'license_url_or_text': license_url_or_text,
                        'collection': collection
                    }
                except:
                    pass

        print(f"  ✓ Extracted from cache: {len(pmcid_to_info)} articles")

        # Fetch missing ones from NCBI
        missing_pmcids = [pmc for pmc in pmcids if pmc not in pmcid_to_info]
        if missing_pmcids:
            print(f"  Fetching {len(missing_pmcids)} missing articles from NCBI...")
            print()
            missing_info = fetch_pmc_license_metadata_batch(missing_pmcids)
            pmcid_to_info.update(missing_info)

        print()
        print(f"  ✓ License metadata retrieved: {len(pmcid_to_info)} articles")
        print()
    else:
        print("Step 2: Fetching license metadata from PMC...")
        print()
        pmcid_to_info = fetch_pmc_license_metadata_batch(pmcids)
        print()
        print(f"  ✓ License metadata retrieved: {len(pmcid_to_info)} articles")
        print()

    # Step 3.5: Download XML files and check full-text availability
    print("Step 3: Checking full-text XML files...")
    print()

    pmcid_fulltext_status = download_pmc_xml_files(pmcid_to_info, xml_cache_dir, use_cache)

    fulltext_count = sum(1 for info in pmcid_fulltext_status.values() if info['has_fulltext'])
    print()
    print(f"  ✓ XML files processed: {len(pmcid_fulltext_status)}")
    print(f"  ✓ Articles with full-text: {fulltext_count} ({fulltext_count*100/len(pmcid_fulltext_status):.1f}%)")
    print()

    # Step 4: Create output records
    print("Step 4: Compiling results...")

    output_records = []
    overlap_count = 0

    for pmid, pmc_id in pmid_to_pmc.items():
        record = pmid_to_record[pmid].copy()
        record['pmcid'] = pmc_id

        # Check if in main-portal (by DOI or PMID)
        in_main_portal = False
        doi = normalize_doi(record.get('doi', ''))
        if doi and doi in main_portal_dois:
            in_main_portal = True
        elif pmid in main_portal_pmids:
            in_main_portal = True

        record['in_main_portal'] = 'Yes' if in_main_portal else 'No'
        if in_main_portal:
            overlap_count += 1

        # Add license information
        if pmc_id in pmcid_to_info:
            info = pmcid_to_info[pmc_id]
            record['license'] = determine_license_category(info)
            record['license_url_or_text'] = info.get('license_url_or_text', '')
            record['is_open_access'] = 'Yes' if info['is_open_access'] else 'No'
        else:
            record['license'] = 'Metadata not retrieved'
            record['license_url_or_text'] = ''
            record['is_open_access'] = 'Unknown'

        # Add full-text availability
        if pmc_id in pmcid_fulltext_status:
            ft_info = pmcid_fulltext_status[pmc_id]
            record['has_fulltext'] = 'Yes' if ft_info['has_fulltext'] else 'No (abstract only)'
            record['xml_file'] = ft_info['xml_file']
        else:
            record['has_fulltext'] = 'Unknown'
            record['xml_file'] = ''

        output_records.append(record)

    # Sort by publication date (most recent first)
    output_records.sort(key=lambda x: x.get('publicationDate', ''), reverse=True)

    # Step 5: Write output
    fieldnames = ['publicationId', 'doi', 'pmid', 'pmcid', 'in_main_portal', 'journal',
                 'publicationDate', 'publicationTitle', 'license', 'is_open_access',
                 'has_fulltext', 'xml_file', 'license_url_or_text',
                 'authors', 'abstract', 'citation']

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(output_records)

    print(f"  ✓ Output written to: {output_file}")
    print()

    # Step 6: Generate statistics
    print("="*80)
    print("RESULTS SUMMARY")
    print("="*80)
    print()

    license_counts = Counter(rec.get('license', 'Unknown') for rec in output_records)

    print("License Distribution:")
    print("-" * 80)
    for license_type, count in license_counts.most_common():
        pct = count * 100 / len(output_records)
        print(f"  {count:3d} ({pct:5.1f}%)  {license_type}")

    print()
    print("-" * 80)

    oa_count = sum(1 for r in output_records if r.get('is_open_access') == 'Yes')
    permissive = sum(count for lic, count in license_counts.items()
                     if 'CC-BY' in lic and 'NC' not in lic and 'ND' not in lic)
    reusable_licenses = {'CC-BY', 'CC-BY-4.0', 'CC-BY-NC', 'CC-BY-SA', 'CC-BY-NC-SA', 'Public Domain'}
    reusable = sum(count for lic, count in license_counts.items() if lic in reusable_licenses)
    fulltext_yes = sum(1 for r in output_records if r.get('has_fulltext') == 'Yes')
    abstract_only = sum(1 for r in output_records if r.get('has_fulltext') == 'No (abstract only)')
    nih_manuscripts = sum(count for lic, count in license_counts.items()
                         if 'NIH Public Access/Author Manuscripts' in lic)
    fair_use = sum(count for lic, count in license_counts.items()
                   if 'Fair use' in lic)

    print(f"Total publications in dataset: {len(all_records)}")
    print(f"Publications with PMC ID: {len(output_records)} ({len(output_records)*100/len(all_records):.1f}%)")
    print()
    print(f"Overlap with main-portal: {overlap_count} ({overlap_count*100/len(output_records):.1f}%)")
    print()
    print(f"Full-text available: {fulltext_yes} ({fulltext_yes*100/len(output_records):.1f}%)")
    print(f"Abstract only: {abstract_only} ({abstract_only*100/len(output_records):.1f}%)")
    print()
    print(f"Publisher Open Access (explicit license): {oa_count} ({oa_count*100/len(output_records):.1f}%)")
    print(f"NIH/Author Manuscripts without explicit license: {nih_manuscripts} ({nih_manuscripts*100/len(output_records):.1f}%)")
    print(f"Fair use (text mining + fair use statement): {fair_use} ({fair_use*100/len(output_records):.1f}%)")
    print()
    print(f"Permissive licenses (CC-BY without NC/ND): {permissive} ({permissive*100/len(output_records):.1f}%)")
    print(f"Reusable for non-commercial application that comply with ShareAlike: {reusable} ({reusable*100/len(output_records):.1f}%)")
    print()

    # Top journals
    journal_counts = Counter(rec.get('journal', 'Unknown') for rec in output_records)
    print("Top 10 journals with PMC full-text:")
    print("-" * 80)
    for journal, count in journal_counts.most_common(10):
        print(f"  {count:3d}  {journal}")

    print()
    print("="*80)
    print("COMPLETE!")
    print("="*80)

if __name__ == '__main__':
    main()
