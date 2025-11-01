import os
import docx
from docx.document import Document as _Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
from docx.shared import Pt, Inches  # <-- Added for formatting

# Configuration
BASE_DIR = r"C:\Users\jorda\PycharmProjects\taxmcp"
INPUT_DIR = os.path.join(BASE_DIR, "itaa1997")
# We only need to inspect one file initially to identify the style patterns
FILE_TO_INSPECT = os.path.join(INPUT_DIR, "C2025C00405VOL01.docx")

def iter_paragraphs_recursive(parent):
    """
    Yields consecutive paragraph objects recursively,
    including those inside tables and nested structures, ensuring thorough inspection.
    """
    # Determine the parent element based on the object type
    if isinstance(parent, _Document):
        # Main document body
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        # Table cell element
        parent_elm = parent._tc
    elif isinstance(parent, Table):
        # If the parent is a Table, iterate through its cells and recurse
        for row in parent.rows:
            for cell in row.cells:
                yield from iter_paragraphs_recursive(cell)
        return  # Stop processing this level once the table is handled
    else:
        return

    if parent_elm is None:
        return

    # Iterate through the children elements (paragraphs and tables) in the parent element
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            # Yield the paragraph
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            # If it's a table, process it recursively by passing the Table object
            table = Table(child, parent)
            yield from iter_paragraphs_recursive(table)

# --- New Helper Functions ---

def format_length(val, unit='pt'):
    """Helper to format length objects (like Pt, Inches) nicely."""
    if val is None:
        return 'Default'
    try:
        if unit == 'pt':
            return f"{val.pt:.1f} pt"
        if unit == 'in':
            return f"{val.inches:.2f}\""
    except AttributeError:
        # Handle cases where val is a simple number
        return str(val)
    return str(val)  # Fallback

def get_heading_level(style_name):
    """Extracts heading level from style name if possible."""
    name = str(style_name).strip()
    if name.startswith('Heading ') and name.split(' ')[-1].isdigit():
        return int(name.split(' ')[-1])
    # Handle 'Heading1', 'Heading2' (no space)
    if name.startswith('Heading') and name[len('Heading'):].isdigit():
        return int(name[len('Heading'):])
    return 'N/A'  # Use 'N/A' for non-headings

# --- Updated Analysis Function ---

def analyze_styles(filepath):
    if not os.path.exists(filepath):
        print(f"Error: File not found at {filepath}")
        return

    print(f"Analyzing styles in {os.path.basename(filepath)}...")

    try:
        doc = docx.Document(filepath)
    except Exception as e:
        print(f"Error opening document: {e}")
        return

    found_styles = {}

    # Iterate through all paragraphs recursively
    for paragraph in iter_paragraphs_recursive(doc):
        style_name = paragraph.style.name
        
        if style_name not in found_styles:
            # --- This is the new, expanded part ---
            # This style is new, let's capture its properties
            style = paragraph.style
            font = style.font
            p_format = style.paragraph_format

            found_styles[style_name] = {
                "count": 0,
                "example": "",
                "heading_level": get_heading_level(style_name),
                "base_style": style.base_style.name if style.base_style else 'N/A',
                "font_name": font.name,
                "font_size": format_length(font.size, 'pt'),
                "font_bold": str(font.bold),  # Convert None/True/False to string
                "font_italic": str(font.italic),
                "font_underline": str(font.underline),
                "left_indent": format_length(p_format.left_indent, 'in'),
                "first_line_indent": format_length(p_format.first_line_indent, 'in'),
                "space_before": format_length(p_format.space_before, 'pt'),
                "space_after": format_length(p_format.space_after, 'pt'),
                "line_spacing": f"{p_format.line_spacing:.2f}" if p_format.line_spacing else 'Default',
            }
            # --- End of new part ---
            
        found_styles[style_name]["count"] += 1

        # Capture an example if we don't have one yet and the text is meaningful
        text = paragraph.text.strip()
        if not found_styles[style_name]["example"] and text:
            # Capture the first 150 characters
            example_text = text[:150] + ("..." if len(text) > 150 else "")
            found_styles[style_name]["example"] = example_text

    print("\n--- Style Analysis Report ---")
    if not found_styles:
        print("No styles/paragraphs found. This is highly unusual for a Word document.")
        return

    # Sort by count descending to see the most common styles first
    sorted_by_count = sorted(found_styles.items(), key=lambda item: item[1]["count"], reverse=True)

    for style, data in sorted_by_count:
        # --- Updated Printout ---
        print(f"\nStyle Name: '{style}'")
        print(f"  Count:             {data['count']}")
        print(f"  Heading Level:     {data['heading_level']}")
        print(f"  Base Style:        {data['base_style']}")
        print(f"  Font:              {data['font_name']}, {data['font_size']}")
        print(f"  Font Attrs:        Bold: {data['font_bold']}, Italic: {data['font_italic']}, Underline: {data['font_underline']}")
        print(f"  Indents (L/1st):   {data['left_indent']} / {data['first_line_indent']}")
        print(f"  Spacing (Bef/Aft): {data['space_before']} / {data['space_after']}")
        print(f"  Line Spacing:      {data['line_spacing']}")
        print(f"  Example:           {data['example']}")
        # --- End of Updated Printout ---

    print("\n----------------------------------")
    print("Please provide this report so the processing script can be updated.")

if __name__ == '__main__':
    # Ensure python-docx is installed (pip install python-docx)
    
    # Uncomment the following line to run the analysis
    analyze_styles(FILE_TO_INSPECT)
    pass