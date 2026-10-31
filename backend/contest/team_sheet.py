"""Typeset the team account slips handed out at a contest: A4, cut along the dashed lines.

The plaintext passwords only exist in the response that created them, so the
caller sends the rows back; nothing here reads or stores a password.
"""
import os
import tempfile

from .statement_pdf import StatementPDFError, escape, run_xelatex

# One team per boxed row in plain black sans. The row height and the 2.6mm
# gap make exactly 30 one-line rows fit a page (31 do not), with room to cut.
TEMPLATE = r"""\documentclass[a4paper,10pt]{article}
\usepackage[fontset=fandol,scheme=plain]{ctex}
\usepackage[a4paper,top=16mm,bottom=10mm,left=12mm,right=12mm,headheight=12pt,headsep=4mm]{geometry}
\usepackage{array}
\usepackage{fancyhdr}
\setsansfont{texgyreheros}[Extension=.otf, UprightFont=*-regular, BoldFont=*-bold,
  ItalicFont=*-italic, BoldItalicFont=*-bolditalic]
% Latin and CJK text alike in sans (CJK sans is FandolHei).
\renewcommand{\familydefault}{\sfdefault}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyhead[L]{\small %%HEADER%%}
\fancyhead[R]{\small 第 \thepage 页}
\setlength{\parindent}{0pt}
\setlength{\tabcolsep}{5pt}
\setlength{\arrayrulewidth}{0.6pt}
\renewcommand{\arraystretch}{1.4}
% Column widths add up to the line: three inner rules and the outer two.
\newcolumntype{C}[1]{>{\raggedright\arraybackslash}p{\dimexpr#1\linewidth-2\tabcolsep-0.6pt\relax}}
\newcommand{\xjurow}[4]{\noindent
  \begin{tabular}{|C{0.27}|C{0.31}|C{0.21}|>{\raggedright\arraybackslash}p{\dimexpr0.21\linewidth-2\tabcolsep-1.2pt\relax}|}
    \hline #1 & #2 & 账号\enspace #3 & 密码\enspace #4 \\ \hline
  \end{tabular}\par\nointerlineskip\vspace{2.6mm}}
\begin{document}
%%ROWS%%
\end{document}
"""


def render_team_sheet(header, teams):
    """LaTeX source with one boxed row per team; every field is user text and is escaped."""
    rows = []
    for team in teams:
        fields = [escape(team["name"]), escape("、".join(team["members"][:3])),
                  escape(team["username"]), escape(team["password"])]
        rows.append(r"\xjurow" + "".join("{" + field + "}" for field in fields))
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
