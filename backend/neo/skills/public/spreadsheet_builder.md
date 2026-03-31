---
name: spreadsheet_builder
description: Create structured Excel spreadsheets with proper formatting
task_types: [excel, spreadsheet, table, data, report, budget, tracker, csv, worksheet]
tools: [create_excel]
---

# Spreadsheet Builder Skill

You are helping the user create an Excel spreadsheet. Follow these guidelines:

## Structure Decisions
1. Determine the appropriate **sheet names** based on the data being organized
2. Choose **column headers** that are clear and descriptive
3. Organize data logically — chronological for time series, alphabetical for lists, grouped for categories

## Formatting Defaults
- Headers: Bold, centered, with blue fill (applied automatically)
- Freeze panes on header row (applied automatically)
- Column widths auto-fit to content (applied automatically)

## Common Patterns
- **Budget**: Columns for Category, Description, Amount, Date, Status
- **Tracker**: Columns for Item, Status, Priority, Due Date, Owner, Notes
- **Report**: Group data by sheet (e.g., "Summary" + "Detail" sheets)
- **Inventory**: Columns for Item, Quantity, Unit Price, Total, Location

## Important
- Always use the `create_excel` tool to generate the file
- Include sample data if the user hasn't provided specific data
- Ask clarifying questions if the structure is ambiguous
- Keep sheet names under 31 characters
