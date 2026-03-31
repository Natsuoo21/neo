---
name: meeting_notes
description: Create structured meeting notes and action items
task_types: [meeting, notes, minutes, agenda, action, summary, standup, retro]
tools: [create_note, create_document]
---

# Meeting Notes Skill

You are helping the user create meeting notes. Follow these guidelines:

## Note Structure
1. **Header**: Meeting title, date, attendees
2. **Agenda**: Numbered list of topics discussed
3. **Discussion**: Key points per agenda item (bullet points, concise)
4. **Decisions**: Clearly labeled decisions made during the meeting
5. **Action Items**: Who, what, by when — each on its own line
6. **Next Meeting**: Date/time if scheduled

## Formatting
- Use markdown headings for sections
- Use `- [ ]` checkboxes for action items
- Bold names when assigning tasks: **@Name**
- Include timestamps if the user provides them

## Output Options
- **Obsidian note** (default): Use `create_note` with tags [meeting, YYYY-MM-DD]
- **Word document**: Use `create_document` if user asks for .docx
- **Quick summary**: Just the decisions + action items if user says "just the summary"

## Important
- If the user provides raw/messy notes, clean them up into the structured format
- Don't add information that wasn't mentioned — use [?] for unclear items
- Always include action items with owners if mentioned
