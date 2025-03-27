"""PDF handling utilities for Q."""

import os
from typing import Tuple, Optional

# Third-party imports for PDF processing
try:
    import fitz  # PyMuPDF
    import pdfplumber
    DEPENDENCIES_INSTALLED = True
except ImportError:
    DEPENDENCIES_INSTALLED = False

from rich.console import Console
from q_cli.utils.constants import DEBUG


def is_pdf_file(file_path: str) -> bool:
    """Check if the file is a PDF based on extension and/or magic."""
    # Check file extension first
    if file_path.lower().endswith('.pdf'):
        return True

    # Try using magic if available
    try:
        import magic
        mime_type = magic.from_file(file_path, mime=True)
        return mime_type == 'application/pdf'
    except ImportError:
        # Fall back to just the extension check if magic is not available
        return False


def check_dependencies() -> Tuple[bool, str]:
    """Check if required PDF processing dependencies are installed."""
    if not DEPENDENCIES_INSTALLED:
        return False, ("PDF processing requires PyMuPDF and pdfplumber. "
                       "Install with: pip install pymupdf pdfplumber")
    return True, ""


def extract_text_from_pdf(
    file_path: str, console: Console
) -> Tuple[bool, str, Optional[bytes]]:
    """Extract text and tables from a PDF file.

    Args:
        file_path: Path to the PDF file
        console: Console for output

    Returns:
        Tuple containing:
        - Success flag (True/False)
        - Extracted text with tables embedded as text
        - Original binary content (not used, only for interface compatibility)
    """
    # First, check dependencies
    deps_installed, error_msg = check_dependencies()
    if not deps_installed:
        if DEBUG:
            console.print(f"[yellow]DEBUG: {error_msg}[/yellow]")
        return False, error_msg, None

    try:
        # Avoid using status context since one may already be active in the parent function
        # Expand the file path (handle ~ and environment variables)
        expanded_path = os.path.expanduser(file_path)
        expanded_path = os.path.expandvars(expanded_path)

        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Processing PDF: {expanded_path}[/yellow]"
            )

        # Make sure the path is absolute
        if not os.path.isabs(expanded_path):
            expanded_path = os.path.join(os.getcwd(), expanded_path)

        # Check if file exists
        if not os.path.exists(expanded_path):
            error_msg = f"PDF file not found: {expanded_path}"
            console.print(f"[red]{error_msg}[/red]")
            return False, error_msg, None

        # Read the original binary content for multimodal use
        if DEBUG:
            console.print(f"[dim]Reading PDF file: {expanded_path}...[/dim]")
        with open(expanded_path, "rb") as f:
            binary_content = f.read()

        # Process with PyMuPDF (main text extraction)
        extracted_text = ""
        page_texts = []

        # First extract text with PyMuPDF - only show in debug mode
        if DEBUG:
            console.print(f"[dim]Extracting text from PDF with PyMuPDF...[/dim]")
        with fitz.open(expanded_path) as doc:
            total_pages = len(doc)
            # Only show detailed progress in debug mode
            if DEBUG:
                console.print(f"[yellow]DEBUG: PDF has {total_pages} pages[/yellow]")
            
            for i, page in enumerate(doc):
                # Show progress only in debug mode
                if DEBUG and (i == 0 or i == total_pages - 1 or total_pages > 20 and i % 20 == 0):
                    console.print(f"[dim]Extracting text from page {i+1}/{total_pages}...[/dim]")
                
                # Extract text from the page
                page_text = page.get_text("text")
                page_texts.append(page_text)

                if DEBUG and (i % 10 == 0 or i == total_pages - 1):
                    console.print(
                        f"[yellow]DEBUG: Extracted {len(page_text)} "
                        f"chars from page {i+1}[/yellow]"
                    )

        # Now extract tables with pdfplumber and add them to the text
        if DEBUG:
            console.print(f"[dim]Extracting tables from PDF with pdfplumber...[/dim]")
        with pdfplumber.open(expanded_path) as pdf:
            total_pages = len(pdf.pages)
            found_tables = False
            
            for i, page in enumerate(pdf.pages):
                # No progress messages for table search to reduce verbosity
                # Only report when tables are actually found
                
                # Extract tables from the page
                tables = page.extract_tables()

                if tables:
                    found_tables = True
                    # Only show table conversion messages in debug mode
                    if DEBUG:
                        console.print(f"[dim]Converting {len(tables)} tables on page {i+1}...[/dim]")
                        console.print(
                            f"[yellow]DEBUG: Found {len(tables)} "
                            f"tables on page {i+1}[/yellow]"
                        )

                    # Convert tables to text representation
                    tables_text = []
                    for table_idx, table in enumerate(tables):
                        # Convert table to markdown format
                        header_cells = [col if col else '' for col in table[0]]
                        md_table = "\n| " + " | ".join(header_cells) + " |\n"
                        sep_cells = ["---" for _ in table[0]]
                        separator = "| " + " | ".join(sep_cells) + " |"
                        md_table += separator + "\n"

                        for row in table[1:]:
                            cells = [cell if cell else '' for cell in row]
                            row_text = "| " + " | ".join(cells) + " |"
                            md_table += row_text + "\n"

                        tables_text.append(md_table)

                    # Embed tables in the text for this page
                    # Just append tables at the end of each page for simplicity
                    page_texts[i] += "\n\n" + "\n\n".join(tables_text)

        # Combine all page texts - only show in debug mode
        if DEBUG:
            if total_pages > 10:
                console.print(f"[dim]Finalizing PDF extraction ({total_pages} pages)...[/dim]")
            else:
                console.print(f"[dim]Finalizing PDF extraction...[/dim]")
            
        extracted_text = "\n\n".join(page_texts)

        if DEBUG:
            console.print(
                f"[yellow]DEBUG: Total extracted text: "
                f"{len(extracted_text)} chars from {total_pages} pages[/yellow]"
            )
            
        # Report if tables were found - only in debug mode
        if found_tables and DEBUG:
            console.print(f"[dim]Tables were detected and extracted as markdown[/dim]")

        # Return success with extracted text and binary content
        return True, extracted_text, binary_content

    except Exception as e:
        error_msg = f"Error processing PDF: {str(e)}"
        if DEBUG:
            console.print(f"[red]DEBUG: {error_msg}[/red]")
            import traceback
            console.print(f"[yellow]DEBUG: {traceback.format_exc()}[/yellow]")
            
        # Try fallback approach for text extraction if pymupdf failed
        try:
            if DEBUG:
                console.print(f"[yellow]Attempting fallback PDF extraction method...[/yellow]")
            extracted_text = ""
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                
                # Only show progress messages in debug mode
                if DEBUG:
                    console.print(f"[dim]Extracting {total_pages} pages with fallback method...[/dim]")
                
                for i, page in enumerate(pdf.pages):
                    # Show minimal progress for large PDFs - only in debug mode
                    if DEBUG and total_pages > 50 and i % 50 == 0 and i > 0:
                        console.print(f"[dim]Processed {i}/{total_pages} pages...[/dim]")
                        
                    # Extract text using pdfplumber only
                    page_text = page.extract_text() or ""
                    if page_text:
                        extracted_text += page_text + "\n\n"
            
            if extracted_text.strip():
                if DEBUG:
                    console.print(f"[green]Successfully extracted text with fallback method[/green]")
                return True, extracted_text, None
        except Exception as fallback_error:
            if DEBUG:
                console.print(f"[red]Fallback extraction also failed: {str(fallback_error)}[/red]")
        
        # Show user-friendly error message
        console.print(f"[red]Failed to extract content from PDF: {file_path}[/red]")
        return False, error_msg, None
