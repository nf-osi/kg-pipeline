## Node embedding pipeline

Node embeddings are generated from the KG RDF using
[PecanPy](https://github.com/krishnanlab/PecanPy) (node2vec), producing low-dimensional vector
representations of every entity in the graph. These are used for similarity search, discovery,
query suggestions, and other downstream applications.

### Overview

```
data/rdf/*.ttl
      │
      ▼ (rdf_to_edgelist.py)
data/embeddings/kg.edgelist   ←── weighted IRI edgelist
      │
      ▼ (PecanPy / node2vec)
data/embeddings/kg.emd        ←── 128-dim node embeddings
```

### Step 1: Edgelist extraction

`scripts/rdf_to_edgelist.py` loads all `.ttl` files from `data/rdf/` and extracts every triple
where both subject and object are IRIs, producing a tab-separated weighted edgelist. Edge weight
is the number of distinct predicates connecting each (subject, object) pair. Literal-object
triples are skipped since literals are not graph nodes.

```bash
make edgelist   # Produces data/embeddings/kg.edgelist

# Exclude rdf:type edges to focus on domain relations only
python scripts/rdf_to_edgelist.py \
  --exclude http://www.w3.org/1999/02/22-rdf-syntax-ns#type
```

Current graph: ~893k edges across ~417k nodes (studies, files, investigators, tools, mutations,
ontology terms, etc.).

### Step 2: Node embeddings

PecanPy [1] runs node2vec random walks over the edgelist and trains Word2Vec embeddings. Output is
word2vec text format: one node IRI per line followed by 128 floats.

```bash
make embeddings   # Produces data/embeddings/kg.emd (~7 min on 16 cores)
```

Key parameters (all overridable on the command line):

| Parameter | Default | Description |
|---|---|---|
| `PECANPY_MODE` | `PreCompFirstOrder` | Graph mode; use `SparseOTF` for very large graphs |
| `PECANPY_DIM` | `128` | Embedding dimensions |
| `PECANPY_WORKERS` | `16` | Parallel workers for Word2Vec training |
| `PECANPY_WALKLEN` | `80` | Random walk length |
| `PECANPY_NUMWALKS` | `10` | Walks per node |
| `PECANPY_P` | `1` | Return parameter |
| `PECANPY_Q` | `1` | In-out parameter |

```bash
# Example: faster run for experimentation
make embeddings PECANPY_NUMWALKS=5 PECANPY_WALKLEN=40
```

### References

1. PecanPy — GitHub: https://github.com/krishnanlab/PecanPy, Paper: https://doi.org/10.1093/bioinformatics/btab122
