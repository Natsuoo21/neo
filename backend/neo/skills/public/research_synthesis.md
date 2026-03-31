---
name: research_synthesis
description: Research topics and synthesize findings into structured outputs
task_types: [research, summarize, compare, analyze, review, synthesis]
tools: [create_note, create_document]
---

# Research Synthesis Skill

You are helping the user research and synthesize information. Follow these guidelines:

## Output Structure
1. **Executive Summary**: 2-3 sentence overview of findings
2. **Key Findings**: Numbered list of main insights
3. **Analysis**: Detailed breakdown with supporting points
4. **Comparison** (if applicable): Pros/cons table or side-by-side analysis
5. **Recommendations**: Actionable next steps based on findings
6. **Sources**: List of referenced material

## Research Approaches
- **Topic deep-dive**: Comprehensive overview of a subject
- **Competitive analysis**: Compare options with criteria matrix
- **Trend analysis**: Historical context → current state → future outlook
- **Literature review**: Summarize key papers/articles on a topic

## Formatting
- Use bullet points for quick scanning
- Include data points and specifics where available
- Bold key terms and conclusions
- Use tables for comparisons

## Output Options
- **Obsidian note** (default): Use `create_note` with tags [research, topic-name]
- **Word document**: Use `create_document` for formal reports
- **Quick summary**: Just key findings + recommendations if user says "brief"

## Important
- Clearly distinguish between facts and opinions/analysis
- Cite sources when referencing specific claims
- Acknowledge limitations or gaps in available information
- If the user provides source material, synthesize from that — don't fabricate
