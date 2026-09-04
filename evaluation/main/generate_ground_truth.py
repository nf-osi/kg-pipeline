import pandas as pd
import yaml
import os
import re
from datetime import datetime

# Points at the release-profile CSVs (KG v0.4 schema), two directories up from
# evaluation/main/. Not yet a pinned/archived "evaluation" snapshot -- see
# CHANGELOG.md for what that still requires.
DATA_DIR = '../../data/csv'
DATASET_ATTRIBUTES_FILE = 'dataset_attributes.yaml'
OUTPUT_FILE = 'eval_tools_ground_auto.yaml'

# Predicate for "is this sample human".
#
# Matches "Homo sapiens" or a standalone "Human", including inside multi-valued
# cells such as "Rattus norvegicus,Homo sapiens" and "Homo sapiens|Mus musculus".
#
# The word boundaries are the point. A plain substring alternation also matches
# "Mus musculus (humanized)", so humanized mouse samples were counted as human.
# \b prevents that: there is no word boundary between "human" and "ized".
HUMAN_SPECIES_PATTERN = r'\b(?:Homo sapiens|Human)\b'

def load_data():
    data = {}
    # KG v0.4: every tool-type table is keyed on resourceId and carries the
    # core Tool fields (resourceName, description, synonyms, ...) directly --
    # there is no more central `resources` table to join through, and
    # `development_investigator.csv` / `development_funder.csv` no longer
    # exist as precomputed exports (join `development` with `investigators`
    # / `funders` instead).
    files = {
        'models': 'animal_models.csv',
        'cell_lines': 'cell_lines.csv',
        'donors': 'donors.csv',
        'reagents': 'genetic_reagents.csv',
        'antibodies': 'antibodies.csv',
        'mutations': 'mutations.csv',
        'mutation_model': 'mutation_model.csv',
        'investigators': 'investigators.csv',
        'funders': 'funders.csv',
        'development': 'development.csv',
        'files': 'files.csv',
        'donor_tool': 'donor_tool.csv',
        'studies': 'studies.csv',
        'observations': 'observations.csv'
    }
    for key, filename in files.items():
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            try:
                data[key] = pd.read_csv(path, low_memory=False)
                # Normalize column names
                data[key].columns = data[key].columns.str.strip().str.replace('"', '')
                # Strip quotes from values
                for col in data[key].columns:
                    if data[key][col].dtype == 'object':
                        data[key][col] = data[key][col].str.strip('"')
            except Exception as e:
                print(f"Error loading {filename}: {e}")
                data[key] = pd.DataFrame()
        else:
            data[key] = pd.DataFrame()
    return data

def get_all_questions():
    if not os.path.exists(DATASET_ATTRIBUTES_FILE):
        return {}
    with open(DATASET_ATTRIBUTES_FILE, 'r') as f:
        config = yaml.safe_load(f)

    questions = {}
    for component in config.get('components', []):
        for q in component.get('questions', []):
            questions[q['id']] = q['question']
    return questions

def clean_ids(id_list):
    return sorted({str(i) for i in id_list if pd.notna(i) and str(i) != ''})

def run_queries(data):
    results = {}

    # resourceId membership per tool type, used to disambiguate rows in
    # tables (like mutation_model) that no longer distinguish animal-model
    # vs. cell-line subjects by column name -- both now carry plain
    # `resourceId`.
    animal_model_ids = set(data['models']['resourceId'].dropna()) if not data['models'].empty else set()
    cell_line_ids = set(data['cell_lines']['resourceId'].dropna()) if not data['cell_lines'].empty else set()

    if not data['cell_lines'].empty and not data['donors'].empty:
        cells_donors = pd.merge(
            data['cell_lines'],
            data['donors'],
            on='donorId',
            how='left',
            suffixes=('_cell', '_donor'),
        )
    else:
        cells_donors = pd.DataFrame()

    # Mutation joins
    if not data['mutations'].empty and not data['mutation_model'].empty:
        mut_joined = pd.merge(data['mutations'], data['mutation_model'], on='mutationId', how='inner')
    else:
        mut_joined = pd.DataFrame()

    # Name -> resourceId lookup, for resolving files.modelSystemName (a plain
    # display name) back to a resourceId. Only animal models and cell lines
    # are named this way (see harmonize_files.py).
    name_to_res = {}
    for df in (data['models'], data['cell_lines']):
        if df.empty:
            continue
        for _, row in df.iterrows():
            rid = row['resourceId']
            if pd.notna(row.get('resourceName')):
                name_to_res[str(row['resourceName']).strip()] = rid
            if pd.notna(row.get('synonyms')):
                for s in str(row['synonyms']).split('|'):
                    name_to_res[s.strip()] = rid

    def names_to_resource_ids(names):
        return clean_ids(name_to_res[n] for n in names if n in name_to_res)

    # --- Mutations Discovery ---

    # MUT-001: ClinVar mutation
    term_mut001 = "NM_000267.3(NF1):c.2041C>T (p.Arg681Ter)"
    if not mut_joined.empty:
        matched = mut_joined[mut_joined['humanClinVarMutation'] == term_mut001]
        results['MUT-001'] = clean_ids(matched['resourceId'].tolist())

    # MUT-002: NF1 floxed mice
    ids_mut002 = []
    if not data['mutations'].empty:
        flox_patterns = r'flox'
        flox_mut_ids = data['mutations'][
            (data['mutations']['mutationMethod'].str.contains(flox_patterns, case=False, na=False)) |
            (data['mutations']['mutationType'].str.contains(flox_patterns, case=False, na=False))
        ]['mutationId'].tolist()
        if flox_mut_ids and not data['mutation_model'].empty:
            matched = data['mutation_model'][data['mutation_model']['mutationId'].isin(flox_mut_ids)]
            ids_mut002.extend(matched[matched['resourceId'].isin(animal_model_ids)]['resourceId'].dropna().tolist())
    if not data['models'].empty:
        ids_mut002.extend(data['models'][data['models']['strainNomenclature'].str.contains('flox', case=False, na=False)]['resourceId'].tolist())
    if ids_mut002:
        results['MUT-002'] = clean_ids(ids_mut002)

    # MUT-003: c.104del sequence variation
    if not mut_joined.empty:
        matched = mut_joined[mut_joined['sequenceVariation'].str.contains('c.104del', case=False, na=False)]
        matched = matched[matched['resourceId'].isin(cell_line_ids)]
        results['MUT-003'] = clean_ids(matched['resourceId'].tolist())

    # MUT-004: splice-site variants
    splice_patterns = r'\+1|\+2|\-1|\-2|splice'
    if not mut_joined.empty:
        matched = mut_joined[
            (mut_joined['humanClinVarMutation'].str.contains(splice_patterns, case=False, na=False)) |
            (mut_joined['mutationType'].str.contains('splice', case=False, na=False))
        ]
        results['MUT-004'] = clean_ids(matched['resourceId'].tolist())

    # MUT-005: Cell lines with mutations in multiple genes
    ids_mut005 = []
    if not mut_joined.empty:
        # Filter to cell line rows only
        mut_cells = mut_joined[mut_joined['resourceId'].isin(cell_line_ids)]
        if not mut_cells.empty:
            # Count unique genes per cell line
            res_gene_counts = mut_cells.groupby('resourceId')['affectedGeneSymbol'].nunique()
            # Find cell lines with mutations in multiple genes (>1)
            ids_mut005.extend(res_gene_counts[res_gene_counts > 1].index.tolist())
    results['MUT-005'] = clean_ids(ids_mut005)

    # MUT-006: Mutations present in both animal models and cell lines
    if not mut_joined.empty:
        am_mutations = set(mut_joined[mut_joined['resourceId'].isin(animal_model_ids)]['mutationId'].dropna())
        cl_mutations = set(mut_joined[mut_joined['resourceId'].isin(cell_line_ids)]['mutationId'].dropna())
        shared_mutations = am_mutations & cl_mutations

        if shared_mutations:
            results['MUT-006'] = sorted([str(mid) for mid in shared_mutations if pd.notna(mid)])

    # --- Animal Models ---

    # AM-001: Optic glioma models
    if not data['models'].empty:
        df = data['models']
        matches = df[
            df['manifestation'].str.contains('Optic Nerve Glioma', case=False, na=False) |
            df['description'].str.contains('optic glioma', case=False, na=False)
        ]
        results['AM-001'] = clean_ids(matches['resourceId'].tolist())

    # AM-002: Energy expenditure
    if not data['models'].empty:
        df = data['models']
        matches = df[df['manifestation'].str.contains('Metabolic Function', case=False, na=False)]
        results['AM-002'] = clean_ids(matches['resourceId'].tolist())

    # AM-003: Non-mouse mammalian models
    if not data['models'].empty:
        df = data['models']
        matches = df[df['backgroundStrain'].str.contains('Ossabaw|Yucatan', case=False, na=False)]
        results['AM-003'] = clean_ids(matches['resourceId'].tolist())

    # AM-004: Manually maintained (requires nuanced interpretation of observation text)
    # Earliest mouse tumor detection is at 120 days (4 months):
    # - Nf1flox/flox;PostnCre(+): 215b4e43-8a99-4702-ab4b-eeeadeeb13a5
    # - Nf14F/4F; DhhCre: eb4aff73-9da2-42b5-8f94-0a6084db75b0

    # AM-005: Transplantation models and related donor cell lines (2-hop)
    if not data['models'].empty and not data['cell_lines'].empty:
        # Find xenograft models
        xenografts = data['models'][data['models']['transplantationDonorId'].notna() | data['models']['transplantationType'].notna()]
        if not xenografts.empty:
            xenograft_ids = clean_ids(xenografts['resourceId'].tolist())

            # Find cell lines from the same donors
            donor_ids = xenografts['transplantationDonorId'].dropna().unique().tolist()
            donor_cell_lines = data['cell_lines'][data['cell_lines']['donorId'].isin(donor_ids)]
            cell_line_result_ids = clean_ids(donor_cell_lines['resourceId'].tolist())

            # Combine both xenografts and their donor cell lines
            results['AM-005'] = clean_ids(xenograft_ids + cell_line_result_ids)

    # AM-006: Café-au-lait spots
    if not data['observations'].empty:
        obs = data['observations']
        # Find observations mentioning café-au-lait or CALM (café-au-lait macules)
        # Case-insensitive search for various spellings
        cafe_pattern = r'café-au-lait|cafe-au-lait|cafe au lait|CALM(?:s)?(?:\s|,|\.)'
        cafe_observations = obs[
            obs['observationText'].str.contains(cafe_pattern, case=False, na=False, regex=True)
        ]

        if not cafe_observations.empty:
            # Get unique resource IDs and filter to only animal models
            resource_ids = set(cafe_observations['resourceId'].dropna().unique().tolist())
            animal_model_result_ids = resource_ids & animal_model_ids
            if animal_model_result_ids:
                results['AM-006'] = sorted(animal_model_result_ids)

    # --- Cell Lines ---

    # CL-001: Plexiform neurofibroma
    if not data['cell_lines'].empty:
        df = data['cell_lines']
        matches = df[df['manifestation'].str.contains('Plexiform Neurofibroma', case=False, na=False)]
        results['CL-001'] = clean_ids(matches['resourceId'].tolist())

    # CL-010: MPNST cell line count.
    #
    # Counted off the structured `manifestation` property, which stores the full
    # label -- the string "MPNST" appears nowhere in that column, so filtering it
    # on the acronym yields 0. Substring-matching the acronym across
    # resourceName/synonyms/description instead yields 36: it picks up 15 rows
    # that mention MPNST without carrying the manifestation, and misses 10 that
    # carry it without spelling out the acronym.
    if not data['cell_lines'].empty:
        df = data['cell_lines']
        matches = df[df['manifestation'].str.contains(
            'Malignant Peripheral Nerve Sheath Tumor', case=False, na=False)]
        results['CL-010'] = len(matches)

    # CL-002: Hybridoma
    if not data['cell_lines'].empty:
        df = data['cell_lines']
        matches = df[df['cellLineCategory'].str.contains('Hybridoma', case=False, na=False)]
        results['CL-002'] = clean_ids(matches['resourceId'].tolist())

    # CL-003: Moved to eval_tools_ground_manual.yaml — defining "normal" requires
    # excluding schwannoma, NF1 knockouts, and certain cell line categories (cancer,
    # transformed, iPSC, etc.) which is better handled by manual curation.

    # CL-004: Black patients
    if not data['cell_lines'].empty:
        df = data['cell_lines']
        matches = df[
            df['race'].str.contains('Black|African', case=False, na=False) &
            (
                df['geneticDisorder'].str.contains('Neurofibromatosis type 1', case=False, na=False) |
                df['resourceName'].str.contains(r'\bNF1\b|Neurofibromin', case=False, na=False, regex=True) |
                df['synonyms'].str.contains(r'\bNF1\b|Neurofibromin', case=False, na=False, regex=True) |
                df['description'].str.contains(r'\bNF1\b|Neurofibromin', case=False, na=False, regex=True)
            )
        ]
        results['CL-004'] = clean_ids(matches['resourceId'].tolist())

    # CL-005: pediatric donors
    def is_pediatric(age_val):
        if pd.isna(age_val): return False
        age_str = str(age_val).lower()
        match = re.search(r'^(\d+)', age_str)
        if match:
            num = float(match.group(1))
            if 'm' in age_str and 'y' not in age_str: return True
            return num < 18
        return False

    if not cells_donors.empty:
        df = cells_donors
        ped_human = df[
            df['age'].apply(is_pediatric) &
            df['species'].str.contains(HUMAN_SPECIES_PATTERN, case=False, na=False)
        ]
        results['CL-005'] = clean_ids(ped_human['resourceId'].tolist())

    # CL-006: Human lung cell lines
    if not cells_donors.empty:
        df = cells_donors
        matches = df[
            (df['organ'].str.contains('Lung', case=False, na=False)) &
            (df['species'].str.contains(HUMAN_SPECIES_PATTERN, case=False, na=False))
        ]
        results['CL-006'] = clean_ids(matches['resourceId'].tolist())

    # CL-007: MPNST cell lines with doubling time < 48h
    if not data['cell_lines'].empty:
        df = data['cell_lines'].copy()
        def parse_doubling_time(val):
            if pd.isna(val): return float('inf')
            val = str(val).lower()
            if 'hour' in val or 'h' in val:
                nums = re.findall(r'\d+(?:\.\d+)?', val)
                if nums: return float(nums[0])
            return float('inf')
        df['dt_hours'] = df['populationDoublingTime'].apply(parse_doubling_time)
        # Filter for MPNST manifestation and PDT < 48h
        matches = df[
            (df['manifestation'].str.contains('MPNST|Malignant Peripheral Nerve Sheath', case=False, na=False)) &
            (df['dt_hours'] < 48)
        ]
        results['CL-007'] = clean_ids(matches['resourceId'].tolist())

    # CL-008: Isogenic pairs that differ only in NF1 status (by exactly 1 mutation)
    if not data['cell_lines'].empty and not data['donors'].empty and not data['mutations'].empty and not data['mutation_model'].empty:
        donors_df = data['donors']
        cls_df = data['cell_lines']
        parent_map = dict(zip(donors_df['donorId'], donors_df['parentDonorId']))

        # Walk parentDonorId chain to find root donor for each donor
        def find_root(did):
            visited = set()
            current = did
            while pd.notna(parent_map.get(current)) and current not in visited:
                visited.add(current)
                current = parent_map[current]
            return current

        # Group donors into families by root
        family_groups = {}
        for did in donors_df['donorId']:
            root = find_root(did)
            family_groups.setdefault(root, set()).add(did)

        # Count mutations per cell line (total and NF1-only)
        cl_mut = data['mutation_model'][data['mutation_model']['resourceId'].isin(cell_line_ids)]
        total_mut_count = cl_mut.groupby('resourceId')['mutationId'].nunique()
        nf1_mut_ids = data['mutations'][data['mutations']['affectedGeneSymbol'] == 'NF1']['mutationId']
        nf1_cl_mut = cl_mut[cl_mut['mutationId'].isin(nf1_mut_ids)]
        nf1_mut_count = nf1_cl_mut.groupby('resourceId')['mutationId'].nunique()

        # Cell lines with exactly 1 total mutation and that mutation is NF1
        one_nf1_only = set(nf1_mut_count[nf1_mut_count == 1].index) & set(total_mut_count[total_mut_count == 1].index)
        # Cell lines with 0 total mutations
        all_cl_ids = set(cls_df['resourceId'])
        zero_mut_ids = all_cl_ids - set(total_mut_count.index)

        # Find families with both 0-mutation and exactly-1-NF1-only-mutation members
        qualifying_ids = []
        for root, family_donors in family_groups.items():
            if len(family_donors) < 2:
                continue
            family_cls = cls_df[cls_df['donorId'].isin(family_donors)]
            if family_cls.empty:
                continue
            zero_mut = family_cls[family_cls['resourceId'].isin(zero_mut_ids)]
            one_mut = family_cls[family_cls['resourceId'].isin(one_nf1_only)]
            if zero_mut.empty or one_mut.empty:
                continue
            # Only pair lines with matching tissue type (tissue, organ, cellLineCategory)
            for _, om in one_mut.iterrows():
                matched_wt = zero_mut[
                    (zero_mut['tissue'].fillna('') == (om['tissue'] if pd.notna(om['tissue']) else '')) &
                    (zero_mut['organ'].fillna('') == (om['organ'] if pd.notna(om['organ']) else '')) &
                    (zero_mut['cellLineCategory'].fillna('') == (om['cellLineCategory'] if pd.notna(om['cellLineCategory']) else ''))
                ]
                if not matched_wt.empty:
                    qualifying_ids.append(om['resourceId'])
                    qualifying_ids.extend(matched_wt['resourceId'].tolist())

        results['CL-008'] = clean_ids(qualifying_ids)

    # CL-009: Different tissues same donor
    if not data['cell_lines'].empty:
        donor_tissues = data['cell_lines'].groupby('donorId')['tissue'].nunique()
        multi_tissue_donors = donor_tissues[donor_tissues > 1].index.tolist()
        results['CL-009'] = clean_ids(data['cell_lines'][data['cell_lines']['donorId'].isin(multi_tissue_donors)]['resourceId'].tolist())

    # --- Reagents & Antibodies ---
    if not data['reagents'].empty:
        df = data['reagents']
        results['GR-001'] = clean_ids(df[df['vectorType'].str.contains('CRISPR', case=False, na=False)]['resourceId'].tolist())
        results['GR-002'] = clean_ids(df[
            (df['vectorType'].str.contains('Lentiviral', case=False, na=False)) &
            (df['vectorType'].str.contains('RNAi', case=False, na=False))
        ]['resourceId'].tolist())
        results['GR-003'] = clean_ids(df[df['promoter'].str.contains('CMV', case=False, na=False)]['resourceId'].tolist())
        results['GR-004'] = clean_ids(df[
            (df['copyNumber'].str.contains('High Copy', case=False, na=False)) &
            (df['insertName'].str.contains('NF1', case=False, na=False) | (df['insertEntrezId'].astype(str) == '4763'))
        ]['resourceId'].tolist())
        mam_markers = ['Puromycin', 'Neomycin', 'G418', 'Hygromycin', 'Blasticidin', 'Zeocin']
        results['GR-005'] = clean_ids(df[df['selectableMarker'].str.contains('|'.join(mam_markers), case=False, na=False)]['resourceId'].tolist())

    if not data['antibodies'].empty:
        df = data['antibodies']
        results['AB-001'] = clean_ids(df[df['reactiveSpecies'].str.contains('Drosophila', case=False, na=False)]['resourceId'].tolist())
        # AB-002: C-terminal antibodies for detecting full-length protein
        results['AB-002'] = clean_ids(df[
            df['targetAntigen'].str.contains('C-term', case=False, na=False)
        ]['resourceId'].tolist())
        # AB-003: Phospho-specific antibodies for PTM studies
        results['AB-003'] = clean_ids(df[
            df['targetAntigen'].str.contains('phospho', case=False, na=False)
        ]['resourceId'].tolist())

    # --- By Investigator ---
    # `development` carries the resourceId <-> investigatorId / funderId
    # edges directly; join in investigator/funder names to filter on.
    dev_inv = pd.DataFrame()
    if not data['development'].empty and not data['investigators'].empty:
        dev_inv = pd.merge(data['development'], data['investigators'], on='investigatorId', how='inner')

    if not dev_inv.empty:
        matches = dev_inv[dev_inv['investigatorName'].str.contains('Piotr Topilko', case=False, na=False)]
        results['PI-001'] = clean_ids(matches['resourceId'].tolist())

    if not data['development'].empty and not data['funders'].empty:
        dev_fund = pd.merge(data['development'], data['funders'], on='funderId', how='inner')
        gff_funders = dev_fund[dev_fund['funderName'].str.contains('Gilbert Family Foundation|GFF', case=False, na=False)]
        results['PI-002'] = int(gff_funders['resourceId'].nunique())

    # --- Cross-Resource ---

    # CR-001 (New): Animal models developed by investigators who also contributed reagents
    if not dev_inv.empty:
        am_invs = set(dev_inv[dev_inv['resourceId'].isin(animal_model_ids)]['investigatorName'])
        gr_res_ids = set(data['reagents']['resourceId'].dropna()) if not data['reagents'].empty else set()
        gr_invs = set(dev_inv[dev_inv['resourceId'].isin(gr_res_ids)]['investigatorName'])
        common_invs = am_invs & gr_invs
        if common_invs:
            results['CR-001'] = clean_ids(
                dev_inv[dev_inv['investigatorName'].isin(common_invs) & dev_inv['resourceId'].isin(animal_model_ids)]['resourceId'].tolist()
            )

    # CR-002: Human cell line with most diverse data types
    if not data['files'].empty:
        files = data['files']
        human_files = files[files['species'].str.contains(HUMAN_SPECIES_PATTERN, case=False, na=False)]
        stats = human_files.groupby('modelSystemName')['dataType'].nunique()
        if not stats.empty:
            max_diverse = stats.max()
            winners = stats[stats == max_diverse].index.tolist()
            results['CR-002'] = names_to_resource_ids(winners)

    # --- Study Discovery ---

    # ST-001: Schwannoma studies
    if not data['studies'].empty:
        schwannoma = data['studies'][
            data['studies']['manifestation'].str.contains('Schwannoma', case=False, na=False)
        ]
        ids = schwannoma['studyId'].dropna().tolist()
        if ids:
            results['ST-001'] = sorted(set(ids))

    # ST-002: MPNST studies with RNA-seq data (study manifestation + file assay)
    if not data['studies'].empty and not data['files'].empty:
        mpnst_ids = set(data['studies'][
            data['studies']['manifestation'].str.contains('MPNST', case=False, na=False)
        ]['studyId'].dropna())
        rnaseq_study_ids = set(data['files'][
            data['files']['assay'].str.contains('^RNA-seq$', case=False, na=False, regex=True)
        ]['studyId'].dropna())
        overlap = mpnst_ids & rnaseq_study_ids
        if overlap:
            results['ST-002'] = sorted(overlap)

    # ST-003: Studies with WGS data from human female subjects (multi-attribute file filter)
    if not data['files'].empty:
        wgs_human_female = data['files'][
            (data['files']['assay'].str.contains('whole genome sequencing', case=False, na=False)) &
            (data['files']['species'].str.contains(HUMAN_SPECIES_PATTERN, case=False, na=False)) &
            (data['files']['sex'].str.contains('Female', case=False, na=False))
        ]
        ids = sorted(set(wgs_human_female['studyId'].dropna()))
        if ids:
            results['ST-003'] = ids

    # ST-004: Schwannomatosis studies with data available
    if not data['studies'].empty:
        schwan_avail = data['studies'][
            (data['studies']['diseaseFocus'].str.contains('Schwannomatosis', case=False, na=False)) &
            (data['studies']['dataStatus'].str.contains('Available', case=False, na=False))
        ]
        ids = schwan_avail['studyId'].dropna().tolist()
        if ids:
            results['ST-004'] = sorted(set(ids))

    # ST-005: pNF studies with drug screening data (study manifestation + file dataType)
    if not data['studies'].empty and not data['files'].empty:
        pnf_ids = set(data['studies'][
            data['studies']['manifestation'].str.contains('Plexiform Neurofibroma', case=False, na=False)
        ]['studyId'].dropna())
        drug_study_ids = set(data['files'][
            data['files']['dataType'].str.contains('drug.?screen', case=False, na=False, regex=True)
        ]['studyId'].dropna())
        overlap = pnf_ids & drug_study_ids
        if overlap:
            results['ST-005'] = sorted(overlap)

    # CR-003: matched model systems (same-donor)
    if not data['models'].empty and not data['cell_lines'].empty:
        # 1. Direct donorId match
        am_d = set(data['models']['donorId'].dropna())
        cl_d = set(data['cell_lines']['donorId'].dropna())
        common_donors = am_d & cl_d
        # 2. Transplantation donor match (xenografts)
        am_trans = set(data['models']['transplantationDonorId'].dropna())
        common_trans = am_trans & cl_d
        ids_cr003 = []
        if common_donors:
            ids_cr003.extend(data['models'][data['models']['donorId'].isin(common_donors)]['resourceId'].tolist())
            ids_cr003.extend(data['cell_lines'][data['cell_lines']['donorId'].isin(common_donors)]['resourceId'].tolist())
        if common_trans:
            ids_cr003.extend(data['models'][data['models']['transplantationDonorId'].isin(common_trans)]['resourceId'].tolist())
            ids_cr003.extend(data['cell_lines'][data['cell_lines']['donorId'].isin(common_trans)]['resourceId'].tolist())
        if ids_cr003:
            results['CR-003'] = clean_ids(ids_cr003)

    return results

def main():
    print("Loading data...")
    data = load_data()
    all_questions = get_all_questions()
    all_ids = list(all_questions.keys())

    print("Running queries...")
    query_results = run_queries(data)

    generated_ids = set(query_results.keys())
    skipped_ids = [qid for qid in all_ids if qid not in generated_ids]

    ground_truth = {}
    for qid in sorted(all_ids):
        if qid in query_results:
            res = query_results[qid]
            if isinstance(res, list):
                res = sorted(list(res))

            ground_truth[qid] = {
                'question': all_questions.get(qid, ""),
                'results': res
            }

    output = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'skipped_questions': skipped_ids,
            'total_questions': len(all_ids),
            'generated_questions': len(generated_ids)
        },
        'ground_truth': ground_truth
    }

    print(f"Writing results to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)
    print(f"Done. Skipped {len(skipped_ids)} questions.")

if __name__ == '__main__':
    main()
