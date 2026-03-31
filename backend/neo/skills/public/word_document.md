---
name: word_document
description: Create professional Word documents with proper structure and formatting
task_types: [document, word, docx, report, memo, letter, proposal]
tools: [create_document]
---

# Word Document Skill

You are helping the user create a Word document. Follow these guidelines:

## Structure Decisions
1. **Title**: Clear, descriptive document title
2. **Headings**: Use markdown-style headings (# for main, ## for sub, ### for sub-sub)
3. **Body**: Well-structured paragraphs with clear topic sentences
4. **Lists**: Use bullet points (- ) for unordered items

## Document Types
- **Report**: Executive summary → sections → conclusion → recommendations
- **Memo**: To/From/Date/Subject header → body → action items
- **Letter**: Date → recipient → salutation → body → closing → signature
- **Proposal**: Problem statement → proposed solution → timeline → budget → next steps

## Formatting Defaults
- Keep paragraphs concise (3-5 sentences)
- Use headings to break up long documents
- Number pages for multi-page documents
- Include date and author when appropriate

## Important
- Always use the `create_document` tool to generate the .docx file
- If the user provides rough notes, organize them into proper document structure
- Ask for clarification on document type if ambiguous
- Never fabricate data — use [PLACEHOLDER] for missing information
