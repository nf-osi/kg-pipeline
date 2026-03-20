#!/usr/bin/env python3
"""Build astabench eval_data.yaml from individual qa_PMC*.yaml files.

Reads all qa_PMC*.yaml files in evaluation/qa/ and concatenates them
into a single eval_data.yaml file for the astabench nf_rag_pubs task.

The output format matches astabench's ground_truth structure:
  ground_truth:
    <question_id>:
      question: str
      pmcid: str
      passage_indices: list[int]
      ideal: str
      choices: list[str]
      correct_choice_index: int
      difficulty: str
      question_type: str
"""

import sys
from pathlib import Path

import yaml


def get_dataset_version(attributes_file):
    """Load dataset version from dataset_attributes.yaml, defaulting to 'draft'."""
    if not attributes_file.exists():
        return 'draft'
    try:
        with open(attributes_file) as f:
            config = yaml.safe_load(f)
            return config.get('metadata', {}).get('version', 'draft')
    except Exception:
        return 'draft'


def main():
    qa_dir = Path(__file__).parent
    output_path = qa_dir.parent.parent / "astabench/astabench/evals/nf_rag_pubs/eval_data.yaml"
    attributes_file = qa_dir / "dataset_attributes.yaml"

    # Load dataset version
    dataset_version = get_dataset_version(attributes_file)

    # Find all qa_PMC*.yaml files
    qa_files = sorted(qa_dir.glob("qa_PMC*.yaml"))
    if not qa_files:
        print("No qa_PMC*.yaml files found", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(qa_files)} QA files")

    # Load and merge all questions
    all_questions = {}
    for qa_file in qa_files:
        with open(qa_file) as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            questions = data.get("questions", [])
        elif isinstance(data, list):
            questions = data
        else:
            print(f"Warning: {qa_file} has unexpected format, skipping", file=sys.stderr)
            continue

        # Get pmid from file-level metadata
        file_pmid = data.get("pmid", "") if isinstance(data, dict) else ""

        for q in questions:
            qid = q["id"]
            if qid in all_questions:
                print(f"Warning: duplicate question ID {qid}, overwriting", file=sys.stderr)

            # Restructure to match astabench ground_truth format
            all_questions[qid] = {
                "question": q["question"],
                "pmcid": q["pmcid"],
                "pmid": str(file_pmid),
                "passage_indices": q["passage_indices"],
                "ideal": q["ideal"],
                "choices": q["choices"],
                "correct_choice_index": q["correct_choice_index"],
                "difficulty": q["difficulty"],
                "question_type": q["question_type"],
                "user_query": q.get("user_query", ""),
                "author": q.get("author", "unknown"),
            }

    # Write to eval_data.yaml
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("# NF Publication RAG Evaluation Data\n")
        f.write("#\n")
        f.write("# Auto-generated from evaluation/qa/qa_PMC*.yaml files\n")
        f.write("# Do not edit manually - run evaluation/qa/build_eval_data.py instead\n")
        f.write("#\n")
        f.write(f"# Questions: {len(all_questions)}\n")
        f.write(f"# Papers: {len(set(q['pmcid'] for q in all_questions.values()))}\n")
        f.write("\n")
        output_data = {
            "metadata": {
                "version": dataset_version,
                "total_questions": len(all_questions),
                "total_papers": len(set(q['pmcid'] for q in all_questions.values()))
            },
            "ground_truth": all_questions
        }
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)

    print(f"Wrote {len(all_questions)} questions to {output_path}")


if __name__ == "__main__":
    main()
