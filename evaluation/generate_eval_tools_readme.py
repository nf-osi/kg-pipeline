#!/usr/bin/env python3
"""
Generate a summary README from eval_tools.yaml

Parses the Research Tools Discovery Evaluation Dataset and creates
a formatted README with statistics, summaries, and organized question lists.
"""

import yaml
import re
from pathlib import Path
from collections import Counter


def parse_yaml(yaml_path):
    """Load and parse the YAML file."""
    with open(yaml_path, 'r') as f:
        return yaml.safe_load(f)


def extract_legend_from_comments(yaml_path):
    """Extract legend definitions from YAML header comments."""
    legend = {
        'level': {},
        'facet_answerable': {},
        'text_search_answerable': {}
    }

    with open(yaml_path, 'r') as f:
        content = f.read()

    # Extract level definitions
    level_section = content.split('level:')[1].split('facet_answerable:')[0] if 'level:' in content else ''
    for line in level_section.split('\n'):
        if '"baseline"' in line.lower() and ' - ' in line:
            legend['level']['baseline'] = line.split(' - ', 1)[1].strip()
        elif '"advanced"' in line.lower() and ' - ' in line:
            legend['level']['advanced'] = line.split(' - ', 1)[1].strip()

    # Extract facet_answerable definitions
    facet_section = content.split('facet_answerable:')[1].split('facet_note:')[0] if 'facet_answerable:' in content else ''
    for line in facet_section.split('\n'):
        if '"yes"' in line.lower() and ' - ' in line:
            legend['facet_answerable']['yes'] = line.split(' - ', 1)[1].strip()
        elif '"partial"' in line.lower() and ' - ' in line:
            legend['facet_answerable']['partial'] = line.split(' - ', 1)[1].strip()
        elif '"no"' in line.lower() and ' - ' in line:
            legend['facet_answerable']['no'] = line.split(' - ', 1)[1].strip()

    # Extract text_search_answerable definitions
    text_section = content.split('text_search_answerable:')[1].split('text_search_note:')[0] if 'text_search_answerable:' in content else ''
    for line in text_section.split('\n'):
        if '"yes"' in line.lower() and ' - ' in line:
            legend['text_search_answerable']['yes'] = line.split(' - ', 1)[1].strip()
        elif '"partial"' in line.lower() and ' - ' in line:
            legend['text_search_answerable']['partial'] = line.split(' - ', 1)[1].strip()
        elif '"no"' in line.lower() and ' - ' in line:
            legend['text_search_answerable']['no'] = line.split(' - ', 1)[1].strip()

    return legend


def load_ground_truth_files(script_dir):
    """Load ground truth files and return question ID sets."""
    ground_truth = {
        'auto': set(),
        'manual': set(),
        'none': set()
    }

    # Load auto-generated ground truth
    auto_path = script_dir / 'main' / 'eval_tools_ground_auto.yaml'
    if auto_path.exists():
        try:
            with open(auto_path, 'r') as f:
                auto_data = yaml.safe_load(f)
            if auto_data and 'ground_truth' in auto_data:
                ground_truth['auto'] = set(auto_data['ground_truth'].keys())
        except Exception as e:
            print(f"  Warning: Could not load {auto_path}: {e}")

    # Load manually maintained ground truth
    manual_path = script_dir / 'main' / 'eval_tools_ground_manual.yaml'
    if manual_path.exists():
        try:
            with open(manual_path, 'r') as f:
                manual_data = yaml.safe_load(f)
            if manual_data and 'ground_truth' in manual_data:
                ground_truth['manual'] = set(manual_data['ground_truth'].keys())
        except Exception as e:
            print(f"  Warning: Could not load {manual_path}: {e}")

    return ground_truth


def extract_persona(user_story):
    """Extract persona from user story in format 'As a {persona}, I want...'"""
    if not user_story or not isinstance(user_story, str):
        return None

    # Match pattern: "As a/an {persona}, I want..."
    match = re.match(r'As (?:a|an) ([^,]+),', user_story, re.IGNORECASE)
    if match:
        persona = match.group(1).strip()

        # Capitalize first letter of each word for consistency
        normalized = ' '.join(word.capitalize() for word in persona.split())

        # Group all researcher variants under "Researcher"
        if 'Researcher' in normalized:
            return 'Researcher'

        # Return other personas as-is
        return normalized
    return None


def count_questions(data, ground_truth=None):
    """Count total questions and various statistics."""
    stats = {
        'total': 0,
        'complete': 0,
        'incomplete': 0,
        'by_complexity': Counter(),
        'by_level': Counter(),
        'by_component': Counter(),
        'by_persona': Counter(),
        'by_demo_priority': Counter(),
        'facet_yes': 0,
        'facet_sort_of': 0,
        'facet_no': 0,
        'text_search_yes': 0,
        'text_search_sort_of': 0,
        'text_search_no': 0,
        'ground_truth_auto': 0,
        'ground_truth_manual': 0,
        'ground_truth_none': 0,
    }

    # Initialize ground truth if not provided
    if ground_truth is None:
        ground_truth = {'auto': set(), 'manual': set(), 'none': set()}

    for component in data['components']:
        component_name = component['name']
        for q in component['questions']:
            stats['total'] += 1
            stats['by_component'][component_name] += 1

            # Check if question is complete (has actual question text)
            if q.get('question', '').strip():
                stats['complete'] += 1
            else:
                stats['incomplete'] += 1

            # Count complexity levels
            if 'complexity' in q:
                stats['by_complexity'][q['complexity']] += 1

            # Count difficulty levels
            if 'level' in q:
                stats['by_level'][q['level']] += 1

            # Count demo priorities
            if 'demo_priority' in q:
                stats['by_demo_priority'][q['demo_priority']] += 1

            # Extract and count personas
            if 'user_story' in q:
                persona = extract_persona(q['user_story'])
                if persona:
                    stats['by_persona'][persona] += 1

            # Count facet answerability
            facet_ans = str(q.get('facet_answerable', '')).lower()
            if facet_ans == 'yes' or facet_ans == 'true':
                stats['facet_yes'] += 1
            elif 'partial' in facet_ans:
                stats['facet_sort_of'] += 1
            elif facet_ans in ('no', 'false'):
                stats['facet_no'] += 1

            # Count text search answerability
            text_ans = str(q.get('text_search_answerable', '')).lower()
            if text_ans == 'yes' or text_ans == 'true':
                stats['text_search_yes'] += 1
            elif 'partial' in text_ans:
                stats['text_search_sort_of'] += 1
            elif text_ans in ('no', 'false'):
                stats['text_search_no'] += 1

            # Count ground truth availability
            q_id = q.get('id')
            if q_id:
                if q_id in ground_truth['manual']:
                    stats['ground_truth_manual'] += 1
                elif q_id in ground_truth['auto']:
                    stats['ground_truth_auto'] += 1
                else:
                    stats['ground_truth_none'] += 1

    return stats


def format_facet_ans(value):
    """Format facet_answerable value for display."""
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    value_str = str(value).lower()
    if 'partial' in value_str:
        return 'Partial'
    elif value_str in ('yes', 'true'):
        return 'Yes'
    elif value_str in ('no', 'false'):
        return 'No'
    return str(value)


def generate_readme(data, stats, legend):
    """Generate README content in markdown format (auto-generated section only)."""
    lines = []

    # Legend (moved to top for easy reference)
    lines.append("### Legend\n")
    lines.append("- **Complexity**: Number of graph hops required (0-hop, 1-hop, 2-hop, 3-hop)")

    # Level legend from YAML comments
    if legend['level']:
        lines.append("- **Level**: Difficulty/capability level of the question")
        for level in ['baseline', 'advanced']:
            if level in legend['level']:
                lines.append(f"  - `{level}`: {legend['level'][level]}")
    else:
        lines.append("- **Level**: ")
        lines.append("  - `baseline`: Baseline functionality established by current portal technologies")
        lines.append("  - `advanced`: Harder questions that push the limits of existing technology")

    # Facet answerable legend from YAML comments
    if legend['facet_answerable']:
        lines.append("- **Facet**: Whether answerable via portal UI facets alone")
        for level in ['yes', 'partial', 'no']:
            if level in legend['facet_answerable']:
                lines.append(f"  - `{level.capitalize()}`: {legend['facet_answerable'][level]}")
    else:
        lines.append("- **Facet**: Whether answerable via portal UI facets alone")

    # Text search answerable legend from YAML comments
    if legend['text_search_answerable']:
        lines.append("- **Text Search**: Whether answerable via MySQL text search today")
        for level in ['yes', 'partial', 'no']:
            if level in legend['text_search_answerable']:
                lines.append(f"  - `{level.capitalize()}`: {legend['text_search_answerable'][level]}")
    else:
        lines.append("- **Text Search**: Whether answerable via MySQL text search today")

    lines.append("")
    lines.append("---\n")

    # Statistics Summary
    lines.append("### Dataset Statistics\n")
    lines.append(f"- **Total Questions**: {stats['total']}")
    lines.append(f"  - Complete: {stats['complete']}")
    lines.append(f"  - Incomplete/WIP: {stats['incomplete']}\n")

    lines.append("#### By Complexity")
    for complexity in sorted(stats['by_complexity'].keys()):
        count = stats['by_complexity'][complexity]
        lines.append(f"- **{complexity}**: {count}")
    lines.append("")

    lines.append("#### By Difficulty Level")
    for level in sorted(stats['by_level'].keys()):
        count = stats['by_level'][level]
        lines.append(f"- **{level}**: {count}")
    lines.append("")

    lines.append("#### By Persona")
    if stats['by_persona']:
        # Sort personas by count (descending), then alphabetically
        sorted_personas = sorted(stats['by_persona'].items(),
                                key=lambda x: (-x[1], x[0]))
        for persona, count in sorted_personas:
            lines.append(f"- **{persona}**: {count}")
        lines.append("")
        lines.append(f"*Total unique personas: {len(stats['by_persona'])}*")
    else:
        lines.append("- *No personas extracted*")
    lines.append("")

    lines.append("#### By Demo Priority")
    if stats['by_demo_priority']:
        # Sort by priority order: high, medium, low, tbd
        priority_order = {'high': 0, 'medium': 1, 'low': 2, 'tbd': 3}
        sorted_priorities = sorted(stats['by_demo_priority'].items(),
                                  key=lambda x: priority_order.get(x[0], 99))
        for priority, count in sorted_priorities:
            lines.append(f"- **{priority}**: {count}")
    else:
        lines.append("- *No demo priorities assigned*")
    lines.append("")

    lines.append("#### Answerability via Current Technologies\n")
    lines.append("| Technology | Yes | Partial | No |")
    lines.append("|------------|-----|---------|-----|")
    lines.append(f"| **Facet Filters** | {stats['facet_yes']} | {stats['facet_sort_of']} | {stats['facet_no']} |")
    lines.append(f"| **Text Search** | {stats['text_search_yes']} | {stats['text_search_sort_of']} | {stats['text_search_no']} |\n")

    lines.append("#### Ground Truth Availability\n")
    lines.append(f"- **Automated** (generated from CSV data): {stats['ground_truth_auto']}")
    lines.append(f"- **Manual** (curated, requires interpretation): {stats['ground_truth_manual']}")
    if stats['ground_truth_none'] > 0:
        lines.append(f"- **Not Yet Available**: {stats['ground_truth_none']}\n")
    else:
        lines.append("")  # Add blank line for consistent spacing

    lines.append("---\n")

    # Components and Questions
    lines.append("### Question Categories\n")

    for component in data['components']:
        name = component['name']
        desc = component['description']
        questions = component['questions']
        complete_count = sum(1 for q in questions if q.get('question', '').strip())
        total_count = len(questions)

        lines.append(f"#### {name}")
        lines.append(f"*{desc}*\n")
        lines.append(f"**Questions: {complete_count}/{total_count} complete**\n")

        # Create table for questions
        if complete_count > 0:
            lines.append("| ID | Question | Level | Complexity | Facet | Text Search |")
            lines.append("|----|----------|-------|------------|-------|-------------|")

            for q in questions:
                question_text = q.get('question', '').strip()
                if not question_text:
                    continue

                q_id = q.get('id', 'N/A')
                # Truncate long questions for table display
                if len(question_text) > 80:
                    question_text = question_text[:77] + "..."

                level = q.get('level', 'N/A')
                complexity = q.get('complexity', 'N/A')
                facet = format_facet_ans(q.get('facet_answerable', 'N/A'))
                text_search = format_facet_ans(q.get('text_search_answerable', 'N/A'))

                lines.append(f"| {q_id} | {question_text} | {level} | {complexity} | {facet} | {text_search} |")

            lines.append("")

        # List incomplete questions if any
        incomplete = [q for q in questions if not q.get('question', '').strip()]
        if incomplete:
            lines.append("**Incomplete/Placeholder Questions:**")
            for q in incomplete:
                q_id = q.get('id', 'Unknown')
                lines.append(f"- {q_id} (TBD)")
            lines.append("")

        lines.append("")

    # Footer
    lines.append("---\n")
    lines.append("*Generated by `evaluation/generate_eval_tools_readme.py`*")

    return '\n'.join(lines)


def update_readme_section(readme_path, new_content):
    """
    Update only the auto-generated section of the README, preserving manual content.

    Looks for markers:
    <!-- BEGIN AUTO-GENERATED SECTION - DO NOT EDIT MANUALLY -->
    <!-- END AUTO-GENERATED SECTION -->

    If markers don't exist, creates a new README with the auto-generated section.
    """
    begin_marker = "<!-- BEGIN AUTO-GENERATED SECTION - DO NOT EDIT MANUALLY -->"
    end_marker = "<!-- END AUTO-GENERATED SECTION -->"

    # Try to read existing README
    if readme_path.exists():
        with open(readme_path, 'r') as f:
            existing_content = f.read()

        # Check if markers exist
        if begin_marker in existing_content and end_marker in existing_content:
            # Extract before and after sections
            before_section = existing_content.split(begin_marker)[0]
            after_section = existing_content.split(end_marker)[1]

            # Reconstruct with new auto-generated content
            updated_content = (
                f"{before_section}"
                f"{begin_marker}\n\n"
                f"{new_content}\n\n"
                f"{end_marker}"
                f"{after_section}"
            )

            print("  ✓ Updated auto-generated section, preserved manual content")
            return updated_content
        else:
            print("  ⚠ No markers found in existing README, creating full file with markers")
    else:
        print("  ℹ No existing README, creating new file with markers")

    # Create new README with markers (when no existing README or markers)
    # Title is H1, auto-generated sections start at H3
    full_content = (
        f"# Research Tools Discovery Evaluation Dataset\n\n"
        f"*Auto-generated from `eval_tools.yaml`*\n\n"
        f"{begin_marker}\n\n"
        f"{new_content}\n\n"
        f"{end_marker}\n"
    )

    return full_content


def main():
    """Main entry point."""
    # Paths (script now in evaluation/ directory)
    script_dir = Path(__file__).parent
    yaml_path = script_dir / 'main' / 'eval_tools.yaml'
    readme_path = script_dir / 'README.md'

    # Parse YAML
    print(f"Reading {yaml_path}...")
    data = parse_yaml(yaml_path)

    # Extract legend from YAML comments
    print("Extracting legend definitions...")
    legend = extract_legend_from_comments(yaml_path)

    # Load ground truth files
    print("Loading ground truth files...")
    ground_truth = load_ground_truth_files(script_dir)

    # Calculate statistics
    print("Calculating statistics...")
    stats = count_questions(data, ground_truth)

    # Generate README content (without header, it will be added by update_readme_section if needed)
    print("Generating README content...")
    readme_content = generate_readme(data, stats, legend)

    # Update README, preserving manual sections
    print(f"Updating {readme_path}...")
    final_content = update_readme_section(readme_path, readme_content)

    with open(readme_path, 'w') as f:
        f.write(final_content)

    print("✓ README updated successfully!")
    print(f"  Total questions: {stats['total']} ({stats['complete']} complete, {stats['incomplete']} incomplete)")


if __name__ == '__main__':
    main()
