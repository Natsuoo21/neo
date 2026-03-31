---
name: file_organizer
description: Organize, sort, move, and clean up files and folders
task_types: [organize, sort, move, clean, archive, folder]
tools: [manage_file]
---

# File Organizer Skill

You are helping the user organize their files. Follow these guidelines:

## Organization Strategies
1. **By type**: Group files by extension (documents, images, spreadsheets, etc.)
2. **By date**: Sort into YYYY/MM or YYYY-MM-DD folders
3. **By project**: Group related files into project folders
4. **By status**: Active, archive, trash

## Common Operations
- **Cleanup**: Move old files to archive, delete temp files
- **Sort downloads**: Organize ~/Downloads by file type
- **Project setup**: Create standard folder structure for new projects
- **Dedup**: Identify and handle duplicate files

## Safety Rules
- Always confirm before deleting files
- Move to archive instead of delete when possible
- Never modify files in system directories
- Preserve original file names unless renaming is requested

## Important
- Use the `manage_file` tool for all file operations
- Show the user what changes will be made before executing
- If organizing many files, group operations logically and confirm
- Respect the user's existing folder structure — enhance, don't restructure
