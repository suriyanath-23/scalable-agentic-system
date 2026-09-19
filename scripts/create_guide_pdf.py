from html.parser import HTMLParser
from pathlib import Path
import re
import textwrap


class TextExtractor(HTMLParser):
    block_tags = {"p", "h1", "h2", "h3", "li", "tr", "pre", "div", "section"}

    def __init__(self):
        super().__init__()
        self.lines = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag in self.block_tags and self.current:
            self.flush()

    def handle_endtag(self, tag):
        if tag in self.block_tags:
            self.flush()

    def handle_data(self, data):
        cleaned = re.sub(r"\s+", " ", data).strip()
        if cleaned:
            self.current.append(cleaned)

    def flush(self):
        text = " ".join(self.current).strip()
        if text:
            self.lines.append(text)
        self.current = []


def pdf_escape(text):
    replacements = {"\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "}
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(source, destination):
    parser = TextExtractor()
    parser.feed(Path(source).read_text(encoding="utf-8"))
    lines = []
    for line in parser.lines:
        width = 92 if not line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")) else 88
        lines.extend(textwrap.wrap(line, width=width) or [""])

    page_lines = 49
    pages = [lines[index:index + page_lines] for index in range(0, len(lines), page_lines)]
    objects = []
    page_ids = []
    content_ids = []

    def add_object(value):
        objects.append(value)
        return len(objects)

    catalog_id = add_object(None)
    pages_id = add_object(None)
    font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_number, page in enumerate(pages, 1):
        commands = ["BT", "/F1 10 Tf", "42 780 Td", "13 TL"]
        for line in page:
            commands.append(f"({pdf_escape(line)}) Tj T*")
        commands.extend(["ET"])
        content = "\n".join(commands).encode("latin-1", "replace")
        content_id = add_object(f"<< /Length {len(content)} >>\nstream\n{content.decode('latin-1')}\nendstream")
        content_ids.append(content_id)
        page_id = add_object(None)
        page_ids.append(page_id)

    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>"
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(page_ids)} >>"
    for page_id, content_id in zip(page_ids, content_ids):
        objects[page_id - 1] = f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n{value}\nendobj\n".encode("latin-1", "replace"))
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    Path(destination).write_bytes(output)


if __name__ == "__main__":
    build_pdf("PROJECT_PREPARATION_GUIDE.html", "PROJECT_PREPARATION_GUIDE.pdf")
    print("Created PROJECT_PREPARATION_GUIDE.pdf")
