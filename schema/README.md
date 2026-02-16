# Schema

`ontology.ttl` defines the classes and properties for the NF-OSI knowledge graph.

## External ontology references

The ontology currently uses `owl:sameAs` and `rdfs:subClassOf` to link NF classes to external terms without yet importing full ontologies:

| Prefix | Ontology | Examples |
|--------|----------|-----------------|
| `efo:` | [Experimental Factor Ontology](https://www.ebi.ac.uk/efo/) | See Genotype, Cancer Cell Line, iPSC Line, ESC Line, Animal Model, Wild Type genotype |
| `obo:` | [Sequence Ontology](http://www.sequenceontology.org/) (SO) | See RNAi reagent (`SO:0000337`), sgRNA (`SO:0001998`) |

