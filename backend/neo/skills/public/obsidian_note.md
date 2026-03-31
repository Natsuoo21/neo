---
name: obsidian_note
description: Create well-structured Obsidian notes with frontmatter and linking conventions
task_types: [note, obsidian, journal, daily, zettelkasten, knowledge, wiki, vault]
tools: [create_note]
---

# Obsidian Note Skill

You are helping the user create an Obsidian note. Follow these guidelines:

## Frontmatter Fields
Always include YAML frontmatter with:
- `title` — the note title
- `date` — creation date (YYYY-MM-DD)
- `tags` — relevant topic tags as a list
- `project` — associated project name (if applicable)
- `type` — one of: note, daily, meeting, reference, idea

## Folder Organization
Place notes in the appropriate subfolder:
- `daily/` — daily journal entries (named YYYY-MM-DD.md)
- `projects/` — project-related notes
- `references/` — articles, books, external sources
- `ideas/` — brainstorms, concepts, quick captures

## Backlink Conventions
- Use `[[Note Title]]` to link to related notes
- Use `[[Note Title|display text]]` for custom link text
- Link to the parent project note when relevant
- Add a `## Related` section at the bottom for explicit links

## Content Structure
1. Start with a brief summary or purpose of the note
2. Use headings (`##`, `###`) for clear sections
3. Use bullet lists for quick points, numbered lists for sequences
4. Use `> [!note]` callouts for important information
5. Keep paragraphs short — one idea per paragraph

## Important
- Always use the `create_note` tool to generate the file
- Default to the user's configured Obsidian vault path
- If no tags are provided, suggest 2-3 relevant tags
- Use plain markdown — avoid HTML
