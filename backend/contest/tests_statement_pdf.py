import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from unittest import mock

from django.test import SimpleTestCase, override_settings
from PIL import Image

from .statement_pdf import (ImageStore, LatexRenderer, StatementPDFError, compile_statement_pdf, escape,
                            latex_errors, render_document, text_to_latex)
from .tests_prep import ContestPrepTestBase

PROBLEM = {
    "label": "A", "title": "小红的 #1 数", "description": "<p>给定 $n$，求答案。</p>",
    "input_description": "<p>一行一个整数 $n\\ (1 \\le n \\le 10^5)$。</p>",
    "output_description": "<p>输出答案。</p>", "data_range": "", "hint": "",
    "samples": [{"input": "1 2\n", "output": "3\n", "explanation": "<p>因为 $1+2=3$。</p>"}],
    "time_limit": 1000, "memory_limit": 256, "spj": False,
    "io_mode": {"io_mode": "Standard IO", "input": "input.txt", "output": "output.txt"},
}


class StatementLatexTest(SimpleTestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.workdir)
        self.renderer = LatexRenderer(ImageStore(self.workdir))

    def test_text_is_escaped_and_formulas_pass_through(self):
        self.assertEqual(escape("50% & #1_x {y} ~ ^ \\"),
                         r"50\% \& \#1\_x \{y\} \textasciitilde{} \textasciicircum{} \textbackslash{}")
        self.assertEqual(text_to_latex("令 $a_i \\le 10^9$，且 $$\\sum a$$"), r"令 $a_i \le 10^9$，且 \[\sum a\]")
        # Glyphs the fonts lack become math or real superscripts.
        self.assertEqual(text_to_latex("1 ≤ n ≤ 10⁵"), r"1 $\le$ n $\le$ 10\textsuperscript{5}")
        self.assertEqual(text_to_latex("$n个$"), r"$n\text{个}$")

    def test_formulas_that_could_reach_files_are_shown_as_text(self):
        for formula in ("$\\input{/etc/passwd}$", "$\\immediate\\write18{ls}$", "$^^5cinput x$",
                        "$\\csname input\\endcsname$", "$a}{b$", "$\\def\\x{1}$"):
            rendered = text_to_latex(formula)
            self.assertTrue(rendered.startswith(r"\texttt{"), formula)
            self.assertNotIn("\\input", rendered.replace(r"\textbackslash{}", ""))

    def test_html_structure(self):
        html = ("<p><br>第一行<br>第二行 <strong>粗</strong> <em>斜</em> <u>下划</u> <code>a_b</code></p>"
                "<ul><li>一</li><li><p>二</p></li></ul><ol><li>甲</li></ol><pre><code>for  i\n  x</code></pre>"
                "<script>alert(1)</script>")
        latex = self.renderer.render(html)
        self.assertTrue(latex.startswith("第一行\\newline"))
        for piece in (r"\textbf{粗}", r"\emph{斜}", r"\CJKunderline{下划}", r"\texttt{a\_b}",
                      "\\begin{itemize}\n\\item 一\n\\item 二\n\\end{itemize}", "\\begin{enumerate}",
                      "\\begin{xjucode}\nfor\\ \\ i\\\\\n\\ \\ x\n\\end{xjucode}"):
            self.assertIn(piece, latex)
        self.assertNotIn("alert", latex)

    def test_rendered_katex_gives_back_its_source(self):
        html = ('<p>x <span class="katex"><span class="katex-mathml"><math><semantics><mi>n</mi>'
                '<annotation encoding="application/x-tex">n^2</annotation></semantics></math></span>'
                '<span class="katex-html">n2</span></span></p>')
        self.assertEqual(self.renderer.render(html), "x $n^2$")

    def test_images_are_converted_sized_and_capped(self):
        upload = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, upload)
        Image.new("RGBA", (400, 200), (10, 20, 30, 128)).save(os.path.join(upload, "abc123.webp"), "WEBP")
        with override_settings(UPLOAD_DIR=upload):
            lone = self.renderer.render('<p><img src="/public/upload/abc123.webp" width="50%"></p>')
            inline = self.renderer.render('<p>图 <img src="/public/upload/abc123.webp" height="100"></p>')
            natural = self.renderer.render('<p>x <img src="/public/upload/abc123.webp"></p>')
            missing = self.renderer.render('<p><img src="https://example.com/a.png"></p>'
                                           '<p><img src="/public/upload/../../etc/passwd"></p>')
        self.assertEqual(lone, "\\begin{center}\n\\xjuimage{0.5000\\linewidth}{image1.png}\n\\end{center}")
        self.assertIn(r"\xjuimage{150.00pt}{image1.png}", inline)
        self.assertIn(r"\xjuimage{300.00pt}{image1.png}", natural)
        self.assertEqual(missing.count(r"\xjumissingimage{}"), 2)
        self.assertEqual(os.listdir(self.workdir), ["image1.png"])

    def test_document_carries_header_limits_samples_and_explanations(self):
        problem = dict(PROBLEM, spj=True, time_limit=1500,
                       io_mode={"io_mode": "File IO", "input": "in.txt", "output": "out.txt"})
        source = render_document("2026 CCPC & 校赛", date(2026, 11, 15), [problem], self.workdir,
                                 subtitle="正式赛")
        for piece in (r"2026 CCPC \& 校赛", "2026 年 11 月 15 日", r"\xjuproblem{A}{小红的 \#1 数}",
                      r"\begin{titlepage}", r"{\fontsize{22}{26}\selectfont 正式赛\par}", r"\xjuemblem",
                      r"A & 小红的 \#1 数 \\", "本试题册共 1 题",
                      r"\xjulimit{Time limit:}{1.5 seconds}", r"\xjulimit{Memory limit:}{256 MB}",
                      r"\xjulimit{Input file:}{\texttt{in.txt}}", r"\xjulimit{Special Judge}{}",
                      r"\begin{xjusamples}{in.txt}{out.txt}", r"\xjusamplecell{1\ 2}",
                      r"\xjuexample{Example 1}", r"\xjusection{Explanation}", "因为 $1+2=3$。"):
            self.assertIn(piece, source)
        self.assertNotIn("%%", source.split("\\begin{document}")[1])
        self.assertNotIn("排版生成", source)
        self.assertTrue(os.path.isfile(os.path.join(self.workdir, "xju-emblem.jpg")))

    def test_errors_are_attributed_to_problems(self):
        log = "XJUOJ-PROBLEM:A\nXJUOJ-PROBLEM:B\n! Undefined control sequence.\nl.88 $\\foo\n  x$\n"
        self.assertEqual(latex_errors(log), [{"problem": "B", "message": "Undefined control sequence.",
                                              "context": "l.88 $\\foo x$"}])

    def test_compile_refuses_without_problems_or_xelatex(self):
        with self.assertRaisesMessage(StatementPDFError, "no problems"):
            compile_statement_pdf("Contest", date(2026, 1, 1), [])
        with mock.patch("contest.statement_pdf.shutil.which", return_value=None):
            with self.assertRaisesMessage(StatementPDFError, "XeLaTeX is not installed"):
                compile_statement_pdf("Contest", date(2026, 1, 1), [mock.Mock()])


@unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX is not installed")
class StatementPDFCompileTest(ContestPrepTestBase):
    def test_contest_problems_typeset_into_a_pdf(self):
        self.add_problem(self.contest, title="甲", description="<p>求 $\\sum_{i=1}^n i$ 的值。</p>")
        self.add_problem(self.contest, title="乙")
        from problem.models import Problem
        pdf, errors = compile_statement_pdf("测试赛", date(2026, 5, 1), list(Problem.objects.filter(contest=self.contest)))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(errors, [])


class ContestPrepStatementPDFAPITest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.url = self.reverse("contest_prep_statement_pdf_api")
        self.add_problem(self.contest, title="first")
        self.payload = {"contest_id": self.contest.id, "title": "2026 校赛", "subtitle": "正式赛", "date": "2026-11-15"}

    @mock.patch("contest.views.prep.compile_statement_pdf")
    def test_members_download_the_pdf_with_warnings(self, compile_pdf):
        compile_pdf.return_value = (b"%PDF-1.5 test", [{"problem": "A", "message": "Undefined control sequence.",
                                                        "context": "l.1"}])
        self.login(self.organizer)
        response = self.client.post(self.url, data=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-1.5 test")
        self.assertIn("filename*=UTF-8''2026%20%E6%A0%A1%E8%B5%9B-%E9%A2%98%E9%9D%A2.pdf",
                      response["Content-Disposition"])
        self.assertEqual(json.loads(response["X-Statement-Warnings"]),
                         [{"problem": "A", "message": "Undefined control sequence."}])
        title, contest_date, problems = compile_pdf.call_args.args
        self.assertEqual((title, contest_date, [problem.title for problem in problems]),
                         ("2026 校赛", date(2026, 11, 15), ["first"]))
        self.assertEqual(compile_pdf.call_args.kwargs["subtitle"], "正式赛")

    @mock.patch("contest.views.prep.compile_statement_pdf",
                side_effect=StatementPDFError("Typesetting failed. Problem A: Missing $ inserted."))
    def test_failures_and_strangers_get_errors(self, compile_pdf):
        self.login(self.organizer)
        self.assertFailed(self.client.post(self.url, data=self.payload), "Typesetting failed. Problem A: Missing $ inserted.")
        self.assertFailed(self.client.post(self.url, data=dict(self.payload, date="15/11/2026")))
        self.login(self.stranger)
        self.assertFailed(self.client.post(self.url, data=self.payload), "Contest does not exist")

    def test_one_export_per_contest_at_a_time(self):
        self.login(self.organizer)
        with mock.patch("contest.views.prep.cache.add", return_value=False):
            self.assertFailed(self.client.post(self.url, data=self.payload),
                              "This contest's PDF is already being typeset")


class ImageStoreTest(SimpleTestCase):
    def test_only_existing_uploads_by_plain_name(self):
        upload, work = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, upload)
        self.addCleanup(shutil.rmtree, work)
        buffer = io.BytesIO()
        Image.new("RGB", (3, 3)).save(buffer, "GIF")
        with open(os.path.join(upload, "anim.gif"), "wb") as gif:
            gif.write(buffer.getvalue())
        with override_settings(UPLOAD_DIR=upload):
            store = ImageStore(work)
            self.assertEqual(store.add("/public/upload/anim.gif"), ("image1.png", (3, 3)))
            self.assertEqual(store.add("/public/upload/anim.gif"), ("image1.png", (3, 3)))
            self.assertIsNone(store.add("/public/upload/missing.png"))
            self.assertIsNone(store.add("/public/upload/.hidden.png"))
            self.assertIsNone(store.add("/public/avatar/anim.gif"))
