"""Contest problem statements as a PDF typeset by XeLaTeX, in the olymp style.

Statements are stored as cleaned HTML whose formulas are raw ``$...$`` text, so the HTML is
turned into LaTeX here: text is escaped, formulas are passed to TeX unless they use commands
that could read or write files, and uploaded images are converted to PNG next to the source.
XeLaTeX runs twice (for "Page X of Y") without shell escape and with paranoid file access.
"""
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date as date_type
from html.parser import HTMLParser

from django.conf import settings
from PIL import Image

PDF_TIMEOUT_SECONDS = 60
MARKER = "XJUOJ-PROBLEM"


class StatementPDFError(Exception):
    def __init__(self, message, details=""):
        super().__init__(message)
        self.details = details


# ---------------------------------------------------------------------------
# HTML tree

VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "source", "col", "wbr"}
BLOCK_TAGS = {"p", "div", "ul", "ol", "li", "pre", "blockquote", "table", "hr",
              "h1", "h2", "h3", "h4", "h5", "h6", "center", "section", "article"}
SKIP_TAGS = {"script", "style", "head", "title", "math", "svg"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent

    def text(self):
        return "".join(child if isinstance(child, str) else child.text() for child in self.children)

    def classes(self):
        return (self.attrs.get("class") or "").split()


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {name: value or "" for name, value in attrs}, self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, {name: value or "" for name, value in attrs}, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse_html(value):
    builder = TreeBuilder()
    builder.feed(value or "")
    builder.close()
    return builder.root


# ---------------------------------------------------------------------------
# Text and formulas

ESCAPES = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "#": r"\#", "$": r"\$", "%": r"\%",
    "&": r"\&", "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
    # Text-mode glyphs the statement fonts lack; their math forms look right.
    "≤": r"$\le$", "≥": r"$\ge$", "×": r"$\times$", "≠": r"$\ne$", "÷": r"$\div$",
    "∈": r"$\in$", "∞": r"$\infty$", "→": r"$\to$", "←": r"$\gets$", "−": "-",
    "\u00a0": "~",
}
SUPERSCRIPTS = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ", "0123456789+-=()n"))
SUBSCRIPTS = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎", "0123456789+-=()"))
ESCAPES.update({char: rf"\textsuperscript{{{plain}}}" for char, plain in SUPERSCRIPTS.items()})
ESCAPES.update({char: rf"\textsubscript{{{plain}}}" for char, plain in SUBSCRIPTS.items()})
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MATH = re.compile(r"\$\$(.+?)\$\$|\$([^$]+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]", re.S)
# Commands that read or write files, run code or redefine TeX are never passed through.
UNSAFE_MATH = re.compile(
    r"\\(?:input|include|InputIfFileExists|openin|openout|read|readline|write|message|immediate"
    r"|csname|endcsname|catcode|lccode|uccode|sfcode|mathcode|delcode|chardef|mathchardef|countdef"
    r"|def|edef|gdef|xdef|let|futurelet|global|long|outer|newcommand|renewcommand|providecommand"
    r"|DeclareRobustCommand|NewDocumentCommand|RenewDocumentCommand|newenvironment|renewenvironment"
    r"|usepackage|RequirePackage|documentclass|special|directlua|latelua|loop|newwrite|newread"
    r"|jobname|expandafter|afterassignment|aftergroup|scantokens|every[A-Za-z]*|output|shipout"
    r"|endinput|errmessage|batchmode|nonstopmode|scrollmode|errorstopmode|tracing[A-Za-z]*|dump"
    r"|patterns|hyphenation|font|pdf[A-Za-z]*|XeTeX[A-Za-z]*|begin|end|par|vbox|hbox|setbox"
    r"|halign|valign|noalign|crcr|cr|relax)(?![A-Za-z])")
MATH_SYMBOLS = {"≤": r"\le ", "≥": r"\ge ", "×": r"\times ", "≠": r"\ne ", "÷": r"\div ",
                "·": r"\cdot ", "…": r"\dots ", "−": "-", "∈": r"\in ", "∞": r"\infty ",
                "→": r"\to ", "∑": r"\sum ", "\u00a0": " "}
CJK_RUN = re.compile(r"[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]+")


def escape(text):
    text = CONTROL_CHARS.sub("", text)
    return "".join(ESCAPES.get(char, char) for char in text)


def braces_balanced(body):
    depth = 0
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\":
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
        index += 1
    return depth == 0


def math_to_latex(body, display, raw):
    if "^^" in body or "$" in body or UNSAFE_MATH.search(body) or not braces_balanced(body):
        # Shown as written instead of typeset.
        return r"\texttt{" + escape(raw) + "}"
    body = CONTROL_CHARS.sub("", body)
    body = "".join(MATH_SYMBOLS.get(char)
                   or (f"^{{{SUPERSCRIPTS[char]}}}" if char in SUPERSCRIPTS else None)
                   or (f"_{{{SUBSCRIPTS[char]}}}" if char in SUBSCRIPTS else None)
                   or char for char in body)
    body = CJK_RUN.sub(lambda match: r"\text{" + match.group(0) + "}", body)
    return rf"\[{body}\]" if display else f"${body}$"


def text_to_latex(value, math=True):
    value = re.sub(r"\s+", " ", value)
    if not math:
        return escape(value)
    out = []
    position = 0
    for match in MATH.finditer(value):
        out.append(escape(value[position:match.start()]))
        body = next(group for group in match.groups() if group is not None)
        display = match.group(1) is not None or match.group(4) is not None
        out.append(math_to_latex(body, display, match.group(0)))
        position = match.end()
    out.append(escape(value[position:]))
    return "".join(out)


def verbatim_lines(text, break_long=60):
    """Monospace lines for code blocks and sample cells: spaces kept, long lines breakable."""
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = CONTROL_CHARS.sub("", line.replace("\t", "    "))
        chars = []
        for char in line:
            piece = r"\ " if char == " " else ESCAPES.get(char, char)
            if char in "≤≥×≠÷∈∞→←−":
                piece = char
            chars.append(piece)
        joiner = r"\allowbreak{}" if len(line) > break_long else ""
        lines.append(joiner.join(chars) or r"\mbox{}")
    return lines


# ---------------------------------------------------------------------------
# Images

SIZE_VALUE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(px|%)?\s*$")
UPLOAD_NAME = re.compile(r"^[A-Za-z0-9_-]+\.(?:png|jpe?g|gif|bmp|webp)$", re.I)


class ImageStore:
    """Copies uploaded statement images into the build directory as PNG."""

    def __init__(self, workdir):
        self.workdir = workdir
        self.images = {}

    def add(self, src):
        prefix = settings.UPLOAD_PREFIX.rstrip("/") + "/"
        if not src.startswith(prefix):
            return None
        name = src[len(prefix):]
        if not UPLOAD_NAME.match(name):
            return None
        if name in self.images:
            return self.images[name]
        path = os.path.join(settings.UPLOAD_DIR, name)
        if not os.path.isfile(path):
            return None
        target = f"image{len(self.images) + 1}.png"
        try:
            with Image.open(path) as picture:
                picture.seek(0)
                frame = picture if picture.mode in ("RGB", "RGBA", "L", "LA") else picture.convert("RGBA")
                frame.save(os.path.join(self.workdir, target), "PNG")
                size = picture.size
        except Exception:
            return None
        self.images[name] = (target, size)
        return self.images[name]


# ---------------------------------------------------------------------------
# HTML -> LaTeX

class LatexRenderer:
    def __init__(self, images):
        self.images = images

    def render(self, html):
        return self.blocks(parse_html(html).children).strip()

    # Blocks -------------------------------------------------------------

    def blocks(self, children):
        out = []
        inline = []

        def flush():
            paragraph = self.clean_paragraph("".join(inline))
            if paragraph:
                out.append(paragraph)
            inline.clear()

        for child in children:
            if isinstance(child, Node) and child.tag in SKIP_TAGS:
                continue
            if isinstance(child, Node) and child.tag in BLOCK_TAGS:
                flush()
                rendered = self.block(child)
                if rendered:
                    out.append(rendered)
            else:
                inline.append(self.inline(child))
        flush()
        return "\n\n".join(out)

    @staticmethod
    def clean_paragraph(text):
        text = text.strip()
        # A paragraph may not start or end with a line break.
        text = re.sub(r"^(?:\\newline\s*)+|(?:\s*\\newline)+$", "", text).strip()
        return text

    def block(self, node):
        tag = node.tag
        if tag in ("p", "div", "center", "section", "article"):
            if self.is_lone_image(node):
                return "\\begin{center}\n" + self.inlines(node.children).strip() + "\n\\end{center}"
            return self.blocks(node.children)
        if tag in ("ul", "ol"):
            items = [child for child in node.children if isinstance(child, Node) and child.tag == "li"]
            if not items:
                return ""
            env = "itemize" if tag == "ul" else "enumerate"
            body = "\n".join(r"\item " + (self.blocks(item.children) or r"\mbox{}") for item in items)
            return f"\\begin{{{env}}}\n{body}\n\\end{{{env}}}"
        if tag == "li":
            return self.blocks(node.children)
        if tag == "pre":
            lines = verbatim_lines(node.text().strip("\n"))
            return "\\begin{xjucode}\n" + "\\\\\n".join(lines) + "\n\\end{xjucode}"
        if tag == "blockquote":
            return "\\begin{quote}\n" + self.blocks(node.children) + "\n\\end{quote}"
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            title = self.clean_paragraph(self.inlines(node.children))
            return r"\xjusubheading{" + title + "}" if title else ""
        if tag == "hr":
            return r"\noindent\rule{\linewidth}{0.4pt}"
        if tag == "table":
            return self.table(node)
        return self.blocks(node.children)

    def is_lone_image(self, node):
        meaningful = [child for child in node.children
                      if not (isinstance(child, str) and not child.strip())
                      and not (isinstance(child, Node) and child.tag == "br")]
        return len(meaningful) == 1 and isinstance(meaningful[0], Node) and meaningful[0].tag == "img"

    def table(self, node):
        rows = []
        stack = [node]
        while stack:
            current = stack.pop(0)
            for child in current.children:
                if isinstance(child, Node):
                    if child.tag == "tr":
                        rows.append([cell for cell in child.children
                                     if isinstance(cell, Node) and cell.tag in ("td", "th")])
                    elif child.tag in ("thead", "tbody", "tfoot"):
                        stack.append(child)
        rows = [row for row in rows if row]
        if not rows:
            return ""
        columns = max(len(row) for row in rows)
        width = rf"\dimexpr{0.94 / columns:.4f}\linewidth-2\tabcolsep\relax"
        spec = "|" + "|".join([f"p{{{width}}}"] * columns) + "|"
        lines = []
        for row in rows:
            cells = []
            for cell in row:
                content = self.blocks(cell.children).replace("\n\n", r"\par ")
                cells.append(r"\textbf{" + content + "}" if cell.tag == "th" else content)
            cells += [""] * (columns - len(cells))
            lines.append(" & ".join(cells) + r" \\ \hline")
        return ("\\begin{center}\\small\n\\begin{tabular}{" + spec + "}\n\\hline\n"
                + "\n".join(lines) + "\n\\end{tabular}\n\\end{center}")

    # Inline -------------------------------------------------------------

    def inlines(self, children):
        return "".join(self.inline(child) for child in children)

    def inline(self, child):
        if isinstance(child, str):
            return text_to_latex(child)
        tag = child.tag
        if tag in SKIP_TAGS:
            return ""
        if "katex" in child.classes():
            # Rendered KaTeX that slipped into stored HTML: take its TeX source back.
            source = self.katex_source(child)
            if source is not None:
                display = "katex-display" in child.classes()
                return math_to_latex(source, display, f"${source}$")
        if tag == "br":
            return "\\newline\n"
        if tag == "img":
            return self.image(child)
        if tag in ("strong", "b"):
            return self.wrap(r"\textbf", child)
        if tag in ("em", "i", "cite", "var"):
            return self.wrap(r"\emph", child)
        if tag in ("u", "ins"):
            return self.wrap(r"\CJKunderline", child)
        if tag in ("s", "del", "strike"):
            return self.wrap(r"\CJKsout", child)
        if tag in ("code", "kbd", "samp", "tt"):
            return r"\texttt{" + text_to_latex(child.text(), math=False) + "}"
        if tag == "sup":
            return self.wrap(r"\textsuperscript", child)
        if tag == "sub":
            return self.wrap(r"\textsubscript", child)
        if tag in BLOCK_TAGS:
            # Block content inside inline context (e.g. a table cell): keep as a paragraph run.
            return " " + self.block(child).replace("\n\n", r"\par ") + " "
        return self.inlines(child.children)

    def wrap(self, command, node):
        content = self.inlines(node.children)
        return f"{command}{{{content}}}" if content.strip() else ""

    @staticmethod
    def katex_source(node):
        stack = [node]
        while stack:
            current = stack.pop()
            for child in current.children:
                if isinstance(child, Node):
                    if child.tag == "annotation" and child.attrs.get("encoding") == "application/x-tex":
                        return child.text().strip()
                    stack.append(child)
        return None

    def image(self, node):
        stored = self.images.add(node.attrs.get("src", ""))
        if stored is None:
            return r"\xjumissingimage{}"
        filename, (pixel_width, pixel_height) = stored
        width = SIZE_VALUE.match(node.attrs.get("width", "") or "")
        height = SIZE_VALUE.match(node.attrs.get("height", "") or "")
        if width and width.group(2) == "%":
            size = f"{min(float(width.group(1)), 100) / 100:.4f}\\linewidth"
        elif width:
            size = f"{float(width.group(1)) * 0.75:.2f}pt"
        elif height and height.group(2) != "%" and pixel_height:
            size = f"{float(height.group(1)) * pixel_width / pixel_height * 0.75:.2f}pt"
        else:
            # CSS pixels, as on the web page; the macro caps the width at the column.
            size = f"{pixel_width * 0.75:.2f}pt"
        return rf"\xjuimage{{{size}}}{{{filename}}}"


# ---------------------------------------------------------------------------
# Document

def format_time_limit(milliseconds):
    seconds = milliseconds / 1000
    text = f"{seconds:g}"
    return f"{text} second" if seconds == 1 else f"{text} seconds"


def format_date(value):
    return f"{value.year} 年 {value.month} 月 {value.day} 日"


def sample_rows(samples):
    rows = []
    for sample in samples:
        cells = []
        for key in ("input", "output"):
            lines = verbatim_lines(str(sample.get(key) or "").rstrip("\n"), break_long=40)
            cells.append(r"\xjusamplecell{" + r"\newline ".join(lines) + "}")
        rows.append(" & ".join(cells) + r" \\ \hline")
    return rows


def problem_to_latex(problem, renderer):
    """`problem` is a dict with the Problem fields the statement shows."""
    label = escape(problem["label"])
    title = text_to_latex(problem["title"])
    plain_title = escape(problem["title"])
    io_mode = problem.get("io_mode") or {}
    file_io = io_mode.get("io_mode") == "File IO"
    parts = [
        f"\\typeout{{{MARKER}:{label}}}",
        f"\\xjuproblem{{{label}}}{{{title}}}{{{plain_title}}}",
        r"\begin{xjulimits}",
        r"\xjulimit{Time limit:}{" + format_time_limit(problem["time_limit"]) + "}",
        r"\xjulimit{Memory limit:}{" + f"{problem['memory_limit']} MB" + "}",
    ]
    if file_io:
        parts.append(r"\xjulimit{Input file:}{\texttt{" + escape(io_mode.get("input", "")) + "}}")
        parts.append(r"\xjulimit{Output file:}{\texttt{" + escape(io_mode.get("output", "")) + "}}")
    if problem.get("spj"):
        parts.append(r"\xjulimit{Special Judge}{}")
    parts.append(r"\end{xjulimits}")

    description = renderer.render(problem.get("description") or "")
    if description:
        parts.append(description)
    for heading, field in (("Input", "input_description"), ("Output", "output_description"),
                           ("Constraints", "data_range")):
        content = renderer.render(problem.get(field) or "")
        if content:
            parts.append(rf"\xjusection{{{heading}}}" + "\n" + content)

    samples = [sample for sample in problem.get("samples") or [] if sample.get("input") or sample.get("output")]
    if samples:
        input_name = escape(io_mode.get("input", "")) if file_io else "standard input"
        output_name = escape(io_mode.get("output", "")) if file_io else "standard output"
        parts.append(r"\xjusection{Examples}")
        parts.append(r"\begin{xjusamples}{" + input_name + "}{" + output_name + "}\n"
                     + "\n".join(sample_rows(samples)) + "\n\\end{xjusamples}")
        explanations = []
        for index, sample in enumerate(samples, start=1):
            content = renderer.render(sample.get("explanation") or "")
            if content:
                explanations.append(rf"\xjuexample{{Example {index}}}" + "\n" + content)
        if explanations:
            parts.append(r"\xjusection{Explanation}" + "\n" + "\n\n".join(explanations))

    hint = renderer.render(problem.get("hint") or "")
    if hint:
        parts.append(r"\xjusection{Note}" + "\n" + hint)
    return "\n\n".join(parts)


def render_cover(contest_title, subtitle, contest_date, problems):
    """Title page: name, round, day, emblem and the problem list; it carries no page number."""
    count = len(problems)
    # Long problem lists leave less room for the emblem.
    emblem = 1.0 if count <= 10 else 0.84 if count <= 16 else 0.62 if count <= 22 else 0
    compact = count > 10
    rows = "\n".join(rf"{escape(problem['label'])} & {text_to_latex(problem['title'])} \\" for problem in problems)
    parts = [
        r"\begin{titlepage}",
        r"\centering",
        r"\vspace*{0.2cm}",
        r"{\sffamily\bfseries\fontsize{24}{33}\selectfont\parbox{0.88\textwidth}{\centering "
        + text_to_latex(contest_title, math=False) + r"}\par}",
    ]
    if subtitle:
        parts += [r"\vspace{0.6cm}", r"{\fontsize{22}{26}\selectfont " + text_to_latex(subtitle, math=False) + r"\par}"]
    parts += [r"\vspace{0.5cm}", r"{\large " + format_date(contest_date) + r"\par}"]
    if emblem:
        parts += [r"\vspace{0.9cm}", rf"\scalebox{{{emblem}}}{{\xjuemblem}}\par"]
    parts += [
        r"\vspace{0.8cm}" if emblem else r"\vspace{1.4cm}",
        r"{\sffamily\bfseries\large 试题列表\par}",
        r"\vspace{0.35cm}",
        r"{\small\renewcommand{\arraystretch}{1.06}" if compact else r"{\renewcommand{\arraystretch}{1.18}",
        r"\begin{tabular}{|>{\centering\arraybackslash}p{1.3cm}|>{\centering\arraybackslash}p{7.2cm}|}",
        r"\hline",
        rows,
        r"\hline",
        r"\end{tabular}\par}",
        r"\vspace{0.55cm}",
        r"{\small 本试题册共 " + str(count) + r" 题，" + r"\pageref*{xju-last-page}" + r" 页（不含封面）。\\[2pt]"
        r"如发现缺页或印刷不清，请立即举手示意工作人员。\par}",
        r"\end{titlepage}",
    ]
    return "\n".join(parts)


ASSET_DIR = os.path.join(os.path.dirname(__file__), "statement_assets")


def render_document(contest_title, contest_date, problems, workdir, subtitle=""):
    # TeX may only read the build directory, so the fixed artwork is copied in.
    for name in os.listdir(ASSET_DIR):
        shutil.copy(os.path.join(ASSET_DIR, name), os.path.join(workdir, name))
    renderer = LatexRenderer(ImageStore(workdir))
    body = "\n\n".join(problem_to_latex(problem, renderer) for problem in problems)
    with open(os.path.join(os.path.dirname(__file__), "statement_template.tex"), encoding="utf-8") as template:
        source = template.read()
    return (source.replace("%%CONTEST_TITLE%%", text_to_latex(contest_title, math=False))
                  .replace("%%CONTEST_TITLE_PLAIN%%", escape(contest_title))
                  .replace("%%CONTEST_DATE%%", format_date(contest_date))
                  .replace("%%COVER%%", render_cover(contest_title, subtitle, contest_date, problems))
                  .replace("%%PROBLEMS%%", body))


# ---------------------------------------------------------------------------
# Compilation

def problem_dicts(problems):
    return [{
        "label": problem._id,
        "title": problem.title,
        "description": problem.description,
        "input_description": problem.input_description,
        "output_description": problem.output_description,
        "data_range": problem.data_range,
        "hint": problem.hint,
        "samples": problem.samples or [],
        "time_limit": problem.time_limit,
        "memory_limit": problem.memory_limit,
        "spj": problem.spj,
        "io_mode": problem.io_mode,
    } for problem in problems]


def latex_errors(log):
    """Error messages from a XeLaTeX log, each with the problem it occurred in."""
    errors = []
    problem = None
    lines = log.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(MARKER + ":"):
            problem = line.split(":", 1)[1].strip()
        elif line.startswith("! "):
            context = " ".join(part.strip() for part in lines[index + 1:index + 3] if part.strip())
            errors.append({"problem": problem, "message": line[2:].strip(), "context": context[:200]})
    return errors


def compile_statement_pdf(contest_title, contest_date, problems, subtitle=""):
    """Return (pdf_bytes, errors); errors are recoverable TeX errors worth showing to the setter."""
    if not isinstance(contest_date, date_type):
        raise StatementPDFError("Invalid contest date")
    if not problems:
        raise StatementPDFError("The contest has no problems yet")
    xelatex = shutil.which("xelatex")
    if xelatex is None:
        raise StatementPDFError("PDF export is unavailable: XeLaTeX is not installed on the server")
    with tempfile.TemporaryDirectory(prefix="xjuoj-statements-") as workdir:
        source = render_document(contest_title, contest_date, problem_dicts(problems), workdir, subtitle)
        with open(os.path.join(workdir, "statements.tex"), "w", encoding="utf-8") as tex_file:
            tex_file.write(source)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": workdir,
            "TEXMFOUTPUT": workdir,
            "TEXMFVAR": os.path.join(workdir, ".texmf-var"),
            # No shell escape and no file access outside the build directory.
            "shell_escape": "f",
            "openin_any": "p",
            "openout_any": "p",
            "max_print_line": "1000",
            "LANG": "C.UTF-8",
        }
        command = [xelatex, "-interaction=nonstopmode", "-no-shell-escape", "statements.tex"]
        for _ in range(2):
            try:
                subprocess.run(command, cwd=workdir, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=PDF_TIMEOUT_SECONDS, check=False)
            except subprocess.TimeoutExpired:
                raise StatementPDFError("Typesetting took too long; check the statements for runaway formulas")
        log_path = os.path.join(workdir, "statements.log")
        log = ""
        if os.path.exists(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as log_file:
                log = log_file.read()
        errors = latex_errors(log)
        pdf_path = os.path.join(workdir, "statements.pdf")
        if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
            first = errors[0] if errors else {"problem": None, "message": "no output"}
            where = f"Problem {first['problem']}: " if first.get("problem") else ""
            raise StatementPDFError(f"Typesetting failed. {where}{first['message']}", details=log[-2000:])
        with open(pdf_path, "rb") as pdf_file:
            return pdf_file.read(), errors
