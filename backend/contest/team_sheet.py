"""Typeset the team account slips handed out at a contest: A4, cut along the dashed lines.

The plaintext passwords only exist in the response that created them, so the
caller sends the rows back; nothing here reads or stores a password.
"""
import os
import tempfile

from .statement_pdf import StatementPDFError, escape, run_xelatex

# One team per line, 30 to a page, dashed cut lines between them.
ROWS_PER_PAGE = 30
TEMPLATE = r"""\documentclass[a4paper,10pt]{article}
\usepackage[fontset=fandol,scheme=plain]{ctex}
\usepackage[a4paper,top=16mm,bottom=10mm,left=12mm,right=12mm,headheight=12pt,headsep=4mm]{geometry}
\usepackage{tikz}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyhead[L]{\footnotesize\color{gray}%%HEADER%%}
\fancyhead[R]{\footnotesize\color{gray}第 \thepage 页}
\setlength{\parindent}{0pt}
% No interline glue around the cut lines, so thirty rows always fit a page.
\newcommand{\xjucut}{\par\nointerlineskip\noindent\tikz\draw[dashed,gray!70] (0,0) -- (\linewidth-0.4pt,0);\par\nointerlineskip}
\newcommand{\xjurow}[4]{\noindent%
  \parbox[c][8mm][c]{0.27\linewidth}{\raggedright\small\bfseries #1}\hfill%
  \parbox[c][8mm][c]{0.30\linewidth}{\raggedright\small #2}\hfill%
  \parbox[c][8mm][c]{0.19\linewidth}{\small{\color{gray}账号}\enspace\ttfamily #3}\hfill%
  \parbox[c][8mm][c]{0.19\linewidth}{\small{\color{gray}密码}\enspace\ttfamily #4}\par}
\begin{document}
%%ROWS%%
\end{document}
"""


def render_team_sheet(header, teams):
    """LaTeX source with one line per team; every field is user text and is escaped."""
    rows = []
    for index, team in enumerate(teams):
        if index and index % ROWS_PER_PAGE == 0:
            rows.append(r"\xjucut\newpage")
        fields = [escape(team["name"]), escape("、".join(team["members"][:3])),
                  escape(team["username"]), escape(team["password"])]
        rows.append(r"\xjucut\xjurow" + "".join("{" + field + "}" for field in fields))
    rows.append(r"\xjucut")
    return TEMPLATE.replace("%%HEADER%%", escape(header)).replace("%%ROWS%%", "\n".join(rows))


def compile_team_sheet(header, teams):
    if not teams:
        raise StatementPDFError("No team accounts to print")
    with tempfile.TemporaryDirectory(prefix="xjuoj-teams-") as workdir:
        with open(os.path.join(workdir, "teams.tex"), "w", encoding="utf-8") as tex_file:
            tex_file.write(render_team_sheet(header, teams))
        pdf, log = run_xelatex(workdir, "teams")
        if pdf is None:
            raise StatementPDFError("Typesetting the team sheet failed", details=log[-2000:])
        return pdf
