import pandas as pd
import yaml
import os
import re
from datetime import datetime

# Path adjusted for script location in evaluation/main/
DATA_DIR = '../data/csv'
EVAL_TOOLS_FILE = 'eval_tools.yaml'
OUTPUT_FILE = 'eval_tools_ground_auto.yaml'

def load_data():
    data = {}
    # New filenames without portal_ prefix
    files = {
        'models': 'animal_models.csv',
        'cell_lines': 'cell_lines.csv',
        'donors': 'donors.csv',
        'reagents': 'genetic_reagents.csv',
        'antibodies': 'antibodies.csv',
        'mutations': 'mutations.csv',
        'mutation_model': 'mutation_model.csv',
        'resources': 'resources.csv',
        'investigators': 'development_investigator.csv',
        'funders': 'development_funder.csv',
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
    if not os.path.exists(EVAL_TOOLS_FILE):
        return {}
    with open(EVAL_TOOLS_FILE, 'r') as f:
        config = yaml.safe_load(f)
    
    questions = {}
    for component in config.get('components', []):
        for q in component.get('questions', []):
            questions[q['id']] = q['question']
    return questions

def run_queries(data):
    results = {}
    
    # Pre-compute joins
    if not data['models'].empty and not data['donors'].empty:
        models_donors = pd.merge(
            data['models'],
            data['donors'],
            on='donorId',
            how='left',
            suffixes=('_model', '_donor'),
        )
    else:
        models_donors = pd.DataFrame()
        
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

    if not data['models'].empty and not data['resources'].empty:
        models_resources = pd.merge(
            data['models'],
            data['resources'],
            on='animalModelId',
            how='left',
            suffixes=('', '_resource'),
        )
    else:
        models_resources = pd.DataFrame()

    if not cells_donors.empty and not data['resources'].empty:
        cells_donors_resources = pd.merge(
            cells_donors,
            data['resources'],
            on='cellLineId',
            how='left',
            suffixes=('_cell', '_resource'),
        )
    else:
        cells_donors_resources = pd.DataFrame()

    # Mutation joins
    if not data['mutations'].empty and not data['mutation_model'].empty:
        mut_joined = pd.merge(data['mutations'], data['mutation_model'], on='mutationId', how='inner')
    else:
        mut_joined = pd.DataFrame()

    # Create mapping from primary tool IDs to resourceId using the new resources table
    primary_to_res = {}
    if not data['resources'].empty:
        res = data['resources']
        # Map each tool type ID to the resourceId
        for _, row in res.iterrows():
            rid = row['resourceId']
            for col in ['cellLineId', 'animalModelId', 'antibodyId', 'geneticReagentId']:
                if col in res.columns and pd.notna(row[col]):
                    tid = str(row[col])
                    if tid:
                        if tid not in primary_to_res:
                            primary_to_res[tid] = set()
                        primary_to_res[tid].add(rid)

    # Create mapping from resourceName/synonyms to resourceId
    name_to_res = {}
    if not data['resources'].empty:
        res = data['resources']
        for _, row in res.iterrows():
            rid = row['resourceId']
            # Map primary name
            if pd.notna(row['resourceName']):
                name_to_res[str(row['resourceName']).strip()] = rid
            # Map synonyms
            if pd.notna(row['synonyms']):
                for s in str(row['synonyms']).split('|'):
                    name_to_res[s.strip()] = rid

    def ensure_resource_id(id_list):
        final_ids = set()
        for tid in id_list:
            tid_str = str(tid)
            if tid_str in primary_to_res:
                final_ids.update(primary_to_res[tid_str])
            elif tid_str in name_to_res:
                final_ids.add(name_to_res[tid_str])
            else:
                final_ids.add(tid) # Fallback
        return [i for i in final_ids if pd.notna(i) and i != 'nan' and i != '']

    # --- Mutations Discovery ---

    # MUT-001: ClinVar mutation
    term_mut001 = "NM_000267.3(NF1):c.2041C>T (p.Arg681Ter)"
    if not mut_joined.empty:
        matched = mut_joined[mut_joined['humanClinVarMutation'] == term_mut001]
        ids = []
        ids.extend(matched['animalModelId'].dropna().tolist())
        ids.extend(matched['cellLineId'].dropna().tolist())
        ids = ensure_resource_id(ids)
        if ids:
            results['MUT-001'] = [i for i in set(ids) if pd.notna(i)]

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
            ids_mut002.extend(ensure_resource_id(matched['animalModelId'].dropna().tolist()))
    if not data['models'].empty:
        ids_mut002.extend(ensure_resource_id(data['models'][data['models']['strainNomenclature'].str.contains('flox', case=False, na=False)]['animalModelId'].tolist()))
    if ids_mut002:
        results['MUT-002'] = [i for i in set(ids_mut002) if pd.notna(i)]

    # MUT-003: c.104del sequence variation
    if not mut_joined.empty:
        matched = mut_joined[mut_joined['sequenceVariation'].str.contains('c.104del', case=False, na=False)]
        ids = ensure_resource_id(matched['cellLineId'].dropna().tolist())
        results['MUT-003'] = [i for i in set(ids) if pd.notna(i)]

    # MUT-004: splice-site variants
    splice_patterns = r'\+1|\+2|\-1|\-2|splice'
    ids_mut004 = []
    if not mut_joined.empty:
        matched = mut_joined[
            (mut_joined['humanClinVarMutation'].str.contains(splice_patterns, case=False, na=False)) |
            (mut_joined['mutationType'].str.contains('splice', case=False, na=False))
        ]
        ids_mut004.extend(ensure_resource_id(matched['animalModelId'].dropna().tolist()))
        ids_mut004.extend(ensure_resource_id(matched['cellLineId'].dropna().tolist()))
    if ids_mut004:
        results['MUT-004'] = [i for i in set(ids_mut004) if pd.notna(i)]

    # MUT-005: Cell lines with mutations in multiple genes
    ids_mut005 = []
    if not mut_joined.empty:
        # Filter to cell line rows only
        mut_cells = mut_joined[mut_joined['cellLineId'].notna()]
        if not mut_cells.empty:
            # Count unique genes per cell line
            res_gene_counts = mut_cells.groupby('cellLineId')['affectedGeneSymbol'].nunique()
            # Find cell lines with mutations in multiple genes (>1)
            multi_gene_cell_lines = res_gene_counts[res_gene_counts > 1].index.tolist()
            ids_mut005.extend(ensure_resource_id(multi_gene_cell_lines))
    results['MUT-005'] = [i for i in set(ids_mut005) if pd.notna(i)]

    # MUT-006: Mutations present in both animal models and cell lines
    if not mut_joined.empty:
        am_mutations = set(mut_joined[mut_joined['animalModelId'].notna()]['mutationId'].dropna())
        cl_mutations = set(mut_joined[mut_joined['cellLineId'].notna()]['mutationId'].dropna())
        shared_mutations = am_mutations & cl_mutations

        if shared_mutations:
            results['MUT-006'] = sorted([str(mid) for mid in shared_mutations if pd.notna(mid)])

    # --- Animal Models ---
    
    # AM-001: Optic glioma models
    if not models_resources.empty:
        df = models_resources
        matches = df[
            df['animalModelOfManifestation'].str.contains('Optic Nerve Glioma', case=False, na=False) |
            df['description'].str.contains('optic glioma', case=False, na=False)
        ]
        results['AM-001'] = ensure_resource_id(matches['animalModelId'].tolist())

    # AM-002: Energy expenditure
    if not data['models'].empty:
        df = data['models']
        matches = df[df['animalModelOfManifestation'].str.contains('Metabolic Function', case=False, na=False)]
        results['AM-002'] = ensure_resource_id(matches['animalModelId'].tolist())

    # AM-003: Non-mouse mammalian models
    if not models_donors.empty:
        df = models_donors
        matches = df[df['backgroundStrain'].str.contains('Ossabaw|Yucatan', case=False, na=False)]
        results['AM-003'] = ensure_resource_id(matches['animalModelId'].tolist())

    # AM-004: Manually maintained (requires nuanced interpretation of observation text)
    # Earliest mouse tumor detection is at 120 days (4 months):
    # - Nf1flox/flox;PostnCre(+): 215b4e43-8a99-4702-ab4b-eeeadeeb13a5
    # - Nf14F/4F; DhhCre: eb4aff73-9da2-42b5-8f94-0a6084db75b0

    # AM-005: Transplantation models and related donor cell lines (2-hop)
    if not data['models'].empty and not data['cell_lines'].empty:
        # Find xenograft models
        xenografts = data['models'][data['models']['transplantationDonorId'].notna() | data['models']['transplantationType'].notna()]
        if not xenografts.empty:
            # Get xenograft resourceIds
            xenograft_ids = ensure_resource_id(xenografts['animalModelId'].tolist())

            # Find cell lines from the same donors
            donor_ids = xenografts['transplantationDonorId'].dropna().unique().tolist()
            donor_cell_lines = data['cell_lines'][data['cell_lines']['donorId'].isin(donor_ids)]
            cell_line_ids = ensure_resource_id(donor_cell_lines['cellLineId'].tolist())

            # Combine both xenografts and their donor cell lines
            results['AM-005'] = xenograft_ids + cell_line_ids

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
            # Get unique resource IDs and verify they're animal models
            resource_ids = cafe_observations['resourceId'].dropna().unique().tolist()
            # Filter to only animal models using resources table
            if not data['resources'].empty and resource_ids:
                res = data['resources']
                animal_model_ids = []
                for rid in resource_ids:
                    match = res[res['resourceId'] == rid]
                    if not match.empty and match.iloc[0]['resourceType'] == 'Animal Model':
                        animal_model_ids.append(rid)
                if animal_model_ids:
                    results['AM-006'] = sorted(animal_model_ids)

    # --- Cell Lines ---

    # CL-001: Plexiform neurofibroma
    if not data['cell_lines'].empty:
        df = data['cell_lines']
        matches = df[df['cellLineManifestation'].str.contains('Plexiform Neurofibroma', case=False, na=False)]
        results['CL-001'] = ensure_resource_id(matches['cellLineId'].tolist())

    # CL-002: Hybridoma
    if not data['cell_lines'].empty:
        df = data['cell_lines']
        matches = df[df['cellLineCategory'].str.contains('Hybridoma', case=False, na=False)]
        results['CL-002'] = ensure_resource_id(matches['cellLineId'].tolist())

    # CL-003: normal schwann cell lines
    if not data['cell_lines'].empty:
        df = data['cell_lines']
        matches = df[
            (df['cellLineGeneticDisorder'].str.contains('No known genetic disorder', case=False, na=False)) &
            (df['tissue'].str.contains('schwann', case=False, na=False) | 
             df['cellLineManifestation'].str.contains('schwann', case=False, na=False))
        ]
        if matches.empty:
            matches = df[
                (df['cellLineGeneticDisorder'].str.contains('No known genetic disorder', case=False, na=False)) &
                (df.apply(lambda row: row.astype(str).str.contains('schwann', case=False).any(), axis=1))
            ]
        results['CL-003'] = ensure_resource_id(matches['cellLineId'].tolist())

    # CL-004: Black patients
    if not cells_donors_resources.empty:
        df = cells_donors_resources
        race_series = df.get('race_cell', pd.Series('', index=df.index)).fillna('')
        if 'race_donor' in df.columns:
            race_series = race_series.mask(race_series.eq(''), df['race_donor'].fillna(''))
        matches = df[
            race_series.str.contains('Black|African', case=False, na=False) &
            (
                df['cellLineGeneticDisorder'].str.contains('Neurofibromatosis type 1', case=False, na=False) |
                df['resourceName'].str.contains(r'\bNF1\b|Neurofibromin', case=False, na=False, regex=True) |
                df['synonyms'].str.contains(r'\bNF1\b|Neurofibromin', case=False, na=False, regex=True) |
                df['description'].str.contains(r'\bNF1\b|Neurofibromin', case=False, na=False, regex=True)
            )
        ]
        results['CL-004'] = ensure_resource_id(matches['cellLineId'].tolist())

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
        species_series = df['species_donor'] if 'species_donor' in df.columns else df['species']
        ped_human = df[
            df['age'].apply(is_pediatric) &
            species_series.str.contains('Homo sapiens|Human', case=False, na=False)
        ]
        results['CL-005'] = ensure_resource_id(ped_human['cellLineId'].tolist())

    # CL-006: Human lung cell lines
    if not cells_donors.empty:
        df = cells_donors
        species_series = df['species_donor'] if 'species_donor' in df.columns else df['species']
        matches = df[
            (df['organ'].str.contains('Lung', case=False, na=False)) &
            (species_series.str.contains('Homo sapiens|Human', case=False, na=False))
        ]
        results['CL-006'] = ensure_resource_id(matches['cellLineId'].tolist())

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
            (df['cellLineManifestation'].str.contains('MPNST|Malignant Peripheral Nerve Sheath', case=False, na=False)) &
            (df['dt_hours'] < 48)
        ]
        results['CL-007'] = ensure_resource_id(matches['cellLineId'].tolist())

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
        cl_mut = data['mutation_model'][data['mutation_model']['cellLineId'].notna()]
        total_mut_count = cl_mut.groupby('cellLineId')['mutationId'].nunique()
        nf1_mut_ids = data['mutations'][data['mutations']['affectedGeneSymbol'] == 'NF1']['mutationId']
        nf1_cl_mut = cl_mut[cl_mut['mutationId'].isin(nf1_mut_ids)]
        nf1_mut_count = nf1_cl_mut.groupby('cellLineId')['mutationId'].nunique()

        # Cell lines with exactly 1 total mutation and that mutation is NF1
        one_nf1_only = set(nf1_mut_count[nf1_mut_count == 1].index) & set(total_mut_count[total_mut_count == 1].index)
        # Cell lines with 0 total mutations
        all_cl_ids = set(cls_df['cellLineId'])
        zero_mut_ids = all_cl_ids - set(total_mut_count.index)

        # Find families with both 0-mutation and exactly-1-NF1-only-mutation members
        qualifying_ids = []
        for root, family_donors in family_groups.items():
            if len(family_donors) < 2:
                continue
            family_cls = cls_df[cls_df['donorId'].isin(family_donors)]
            if family_cls.empty:
                continue
            zero_mut = family_cls[family_cls['cellLineId'].isin(zero_mut_ids)]
            one_mut = family_cls[family_cls['cellLineId'].isin(one_nf1_only)]
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
                    qualifying_ids.append(om['cellLineId'])
                    qualifying_ids.extend(matched_wt['cellLineId'].tolist())

        results['CL-008'] = ensure_resource_id(qualifying_ids)

    # CL-009: Different tissues same donor
    if not data['cell_lines'].empty:
        donor_tissues = data['cell_lines'].groupby('donorId')['tissue'].nunique()
        multi_tissue_donors = donor_tissues[donor_tissues > 1].index.tolist()
        results['CL-009'] = ensure_resource_id(data['cell_lines'][data['cell_lines']['donorId'].isin(multi_tissue_donors)]['cellLineId'].tolist())

    # --- Reagents & Antibodies ---
    if not data['reagents'].empty:
        df = data['reagents']
        results['GR-001'] = ensure_resource_id(df[df['vectorType'].str.contains('CRISPR', case=False, na=False)]['geneticReagentId'].tolist())
        results['GR-002'] = ensure_resource_id(df[
            (df['vectorType'].str.contains('Lentiviral', case=False, na=False)) &
            (df['vectorType'].str.contains('RNAi', case=False, na=False))
        ]['geneticReagentId'].tolist())
        results['GR-003'] = ensure_resource_id(df[df['promoter'].str.contains('CMV', case=False, na=False)]['geneticReagentId'].tolist())
        results['GR-004'] = ensure_resource_id(df[
            (df['copyNumber'].str.contains('High Copy', case=False, na=False)) &
            (df['insertName'].str.contains('NF1', case=False, na=False) | (df['insertEntrezId'].astype(str) == '4763'))
        ]['geneticReagentId'].tolist())
        mam_markers = ['Puromycin', 'Neomycin', 'G418', 'Hygromycin', 'Blasticidin', 'Zeocin']
        results['GR-005'] = ensure_resource_id(df[df['selectableMarker'].str.contains('|'.join(mam_markers), case=False, na=False)]['geneticReagentId'].tolist())

    if not data['antibodies'].empty:
        df = data['antibodies']
        results['AB-001'] = ensure_resource_id(df[df['reactiveSpecies'].str.contains('Drosophila', case=False, na=False)]['antibodyId'].tolist())
        # AB-002: C-terminal antibodies for detecting full-length protein
        results['AB-002'] = ensure_resource_id(df[
            df['targetAntigen'].str.contains('C-term', case=False, na=False)
        ]['antibodyId'].tolist())
        # AB-003: Phospho-specific antibodies for PTM studies
        results['AB-003'] = ensure_resource_id(df[
            df['targetAntigen'].str.contains('phospho', case=False, na=False)
        ]['antibodyId'].tolist())

    # --- By Investigator ---
    if not data['investigators'].empty:
        matches = data['investigators'][data['investigators']['investigatorName'].str.contains('Piotr Topilko', case=False, na=False)]
        results['PI-001'] = [i for i in set(matches['resourceId'].dropna().unique().tolist()) if pd.notna(i)]

    if not data['funders'].empty:
        gff_funders = data['funders'][data['funders']['funderName'].str.contains('Gilbert Family Foundation|GFF', case=False, na=False)]
        results['PI-002'] = int(gff_funders['resourceId'].nunique())

    # --- Cross-Resource ---

    # CR-001 (New): Animal models developed by investigators who also contributed reagents
    if not data['investigators'].empty and not data['resources'].empty:
        res = data['resources']
        am_res_ids = set(res[res['animalModelId'].notna()]['resourceId'])
        gr_res_ids = set(res[res['geneticReagentId'].notna()]['resourceId'])
        inv_df = data['investigators']
        am_invs = set(inv_df[inv_df['resourceId'].isin(am_res_ids)]['investigatorName'])
        gr_invs = set(inv_df[inv_df['resourceId'].isin(gr_res_ids)]['investigatorName'])
        common_invs = am_invs & gr_invs
        if common_invs:
            results['CR-001'] = [rid for rid in set(inv_df[inv_df['investigatorName'].isin(common_invs) & inv_df['resourceId'].isin(am_res_ids)]['resourceId'].tolist()) if pd.notna(rid)]

    # CR-002: Human cell line with most diverse data types
    if not data['files'].empty:
        files = data['files']
        human_files = files[files['species'].str.contains('Homo sapiens|Human', case=False, na=False)]
        stats = human_files.groupby('modelSystemName')['dataType'].nunique()
        if not stats.empty:
            max_diverse = stats.max()
            winners = stats[stats == max_diverse].index.tolist()
            results['CR-002'] = ensure_resource_id(winners)

    # CR-003: matched model systems (same-donor)
    if not data['models'].empty and not data['cell_lines'].empty:
        # 1. Direct donorId match
        am_d = set(data['models']['donorId'].dropna())
        cl_d = set(data['cell_lines']['donorId'].dropna())
        common_donors = am_d & cl_d
        # 2. Transplantation donor match (xenografts)
        am_trans = set(data['models']['transplantationDonorId'].dropna())
        common_trans = am_trans & cl_d
        ids_cr003_models = []
        ids_cr003_cells = []
        if common_donors:
            ids_cr003_models.extend(data['models'][data['models']['donorId'].isin(common_donors)]['animalModelId'].tolist())
            ids_cr003_cells.extend(data['cell_lines'][data['cell_lines']['donorId'].isin(common_donors)]['cellLineId'].tolist())
        if common_trans:
            ids_cr003_models.extend(data['models'][data['models']['transplantationDonorId'].isin(common_trans)]['animalModelId'].tolist())
            ids_cr003_cells.extend(data['cell_lines'][data['cell_lines']['donorId'].isin(common_trans)]['cellLineId'].tolist())
        final_cr003 = set()
        if ids_cr003_models:
            final_cr003.update(ensure_resource_id(ids_cr003_models))
        if ids_cr003_cells:
            final_cr003.update(ensure_resource_id(ids_cr003_cells))
        if final_cr003:
            results['CR-003'] = [i for i in final_cr003 if pd.notna(i)]

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
