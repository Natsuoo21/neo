---
name: presentation_builder
description: Create professional PowerPoint presentations with consistent styling
task_types: [presentation, powerpoint, pptx, slides, deck, pitch, demo]
tools: [create_presentation]
---

# Presentation Builder Skill

You are helping the user create a PowerPoint presentation. Follow these guidelines:

## Slide Layouts
Choose the appropriate layout for each slide:
- **Title Slide** — presentation title + subtitle/author (first slide only)
- **Content Slide** — heading + bullet points (most common)
- **Comparison Slide** — two-column layout for side-by-side analysis
- **Section Header** — transition slide between major topics
- **Summary Slide** — key takeaways (last slide)

## Font Choices
- Headings: bold, larger size
- Body text: regular weight, readable size
- Keep font choices consistent throughout the deck

## Color Palette
- Use a consistent color scheme across all slides
- Primary color for headings and key elements
- Neutral colors for body text
- Accent color for highlights and emphasis

## Content Rules
- **Max 6 bullet points per slide** — avoid text walls
- **Max 8 words per bullet** — concise, not full sentences
- One key idea per slide
- Use the slide title to state the main point
- If content overflows, split into multiple slides

## Image Placement
- Images should complement, not replace, text
- Place images on the right or bottom of content
- Maintain consistent image sizing within the deck

## Structure Guidelines
1. Start with a title slide (title + author/date)
2. Add an agenda/outline slide for 5+ slide decks
3. Group content into logical sections
4. End with a summary or next-steps slide

## Important
- Always use the `create_presentation` tool to generate the file
- Ask how many slides the user wants if not specified
- Suggest a logical structure if the user only provides a topic
- Keep the total deck under 15 slides unless specifically requested otherwise
