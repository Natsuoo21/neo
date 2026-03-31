"""PowerPoint tool — Create and edit .pptx files via python-pptx."""

import os

from pptx import Presentation

from neo.tools.paths import resolve_path


def create_presentation(title: str, slides: list[dict] | None = None) -> str:
    """Create a new PowerPoint presentation.

    Args:
        title: Filename (without extension) or full path.
        slides: List of dicts with keys: title (str), content (str).

    Returns:
        Absolute path to the created .pptx file.
    """
    prs = Presentation()

    if not slides:
        # Single title slide — use basename, not full path
        layout = prs.slide_layouts[0]  # Title Slide
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = os.path.basename(title)
        if slide.placeholders[1]:
            slide.placeholders[1].text = "Created by Neo"
    else:
        for i, slide_def in enumerate(slides):
            slide_title = slide_def.get("title", f"Slide {i + 1}")
            slide_content = slide_def.get("content", "")

            if i == 0:
                # First slide: Title layout
                layout = prs.slide_layouts[0]
                slide = prs.slides.add_slide(layout)
                slide.shapes.title.text = slide_title
                if len(slide.placeholders) > 1 and slide.placeholders[1]:
                    slide.placeholders[1].text = slide_content
            else:
                # Content slides: Title + Content layout
                layout = prs.slide_layouts[1]
                slide = prs.slides.add_slide(layout)
                slide.shapes.title.text = slide_title
                if len(slide.placeholders) > 1:
                    body = slide.placeholders[1]
                    tf = body.text_frame
                    tf.text = slide_content

    file_path = resolve_path(title, ".pptx")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    prs.save(file_path)
    return file_path
