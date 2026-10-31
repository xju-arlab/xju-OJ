"""Portable AI problem packages. Pure data parsing; never imports package code."""
import base64
import hashlib
import io
import json
import math
import re
import stat
import zipfile
import zlib
from pathlib import PurePosixPath

FORMAT = "xju-ai-problem"
MAX_UPLOAD = 16 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
MAX_MEMBERS = 1024
MAX_PROBLEMS = 20
STATEMENT_FIELDS = ("objective", "signature", "inputSpec", "outputSpec", "data", "evaluation")
EVALUATION_FIELDS = {"public_column", "private_column", "accuracy_column", "pass_score", "run_seconds", "max_attempts"}
ASSET_FOLDERS = {"scoring_program": "scoring", "ingestion_program": "ingestion", "input_data": "input", "reference_data": "reference"}
TYPES = ("logic", "model", "challenge", "quiz")
QUIZ_KINDS = ("single", "multiple", "number", "order")
QUIZ_ID = r"[A-Za-z0-9_-]{1,32}"
# Quiz images are inlined as data URIs, so keep them small. SVG is never accepted.
MEDIA_TYPES = {"png": ("image/png", (b"\x89PNG\r\n\x1a\n",)), "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
               "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)), "webp": ("image/webp", (b"RIFF",))}
MAX_MEDIA_FILE = 400 * 1024
MAX_MEDIA_TOTAL = 1024 * 1024
MAX_MEDIA_FILES = 8


class PackageError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PackageError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "JSON 中存在重复字段")
        result[key] = value
    return result


def read_json(raw):
    def invalid(_value):
        raise PackageError("JSON 不允许 NaN 或 Infinity")
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=invalid)
        json.dumps(value, ensure_ascii=False).encode("utf-8")  # Reject escaped, unpaired Unicode surrogates.
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PackageError("JSON 格式无效") from exc


def statement_input(value):
    require(isinstance(value, dict) and not set(value) - {*STATEMENT_FIELDS, "requirements"}, "题面字段无效")
    result = {}
    for key in STATEMENT_FIELDS:
        text = value.get(key, "")
        require(isinstance(text, str) and len(text) <= 32000 and "\x00" not in text, "题面必须为有界纯文本")
        result[key] = text
    rules = value.get("requirements", [])
    require(isinstance(rules, list) and len(rules) <= 50 and
            all(isinstance(item, str) and len(item) <= 2000 and "\x00" not in item for item in rules), "实现要求格式无效")
    result["requirements"] = rules
    return result


def evaluation_input(value):
    require(isinstance(value, dict) and not set(value) - EVALUATION_FIELDS, "评测配置字段无效；题包不能绑定服务器 Phase ID")
    result = {"public_column": value.get("public_column", "score"), "pass_score": value.get("pass_score", 100),
              "run_seconds": value.get("run_seconds", 120)}
    for key in ("private_column", "accuracy_column"):
        if value.get(key):
            result[key] = value[key]
    columns = [result[k] for k in ("public_column", "private_column", "accuracy_column") if k in result]
    require(all(isinstance(v, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", v) for v in columns), "评分列名无效")
    require(len(set(columns)) == len(columns), "评分列不能重复")
    require(type(result["pass_score"]) in (int, float) and math.isfinite(result["pass_score"]) and
            0 <= result["pass_score"] <= 100, "达标分数必须在 0–100 之间")
    require(type(result["run_seconds"]) is int and 5 <= result["run_seconds"] <= 600, "运行时限必须在 5–600 秒之间")
    if "max_attempts" in value:
        require(type(value["max_attempts"]) is int and 1 <= value["max_attempts"] <= 20, "比赛提交次数必须在 1–20 之间")
        result["max_attempts"] = value["max_attempts"]
    return result


def _text(value, limit, message, empty=False):
    require(isinstance(value, str) and "\x00" not in value and len(value) <= limit and (empty or value.strip()), message)
    return value


def _cell(value):
    if isinstance(value, str):
        return _text(value, 500, "表格单元格过长", empty=True)
    require(type(value) in (int, float) and math.isfinite(value), "表格单元格必须是文本或有限数值")
    return value


def quiz_input(value):
    """Validate the public answer card: shared materials and auto-graded questions."""
    require(isinstance(value, dict) and not set(value) - {"materials", "questions"}, "作答卡字段无效")
    materials, ids = [], set()
    raw = value.get("materials", [])
    require(isinstance(raw, list) and len(raw) <= 20, "材料最多 20 项")
    for item in raw:
        require(isinstance(item, dict) and item.get("kind") in ("table", "text", "image"), "材料类型必须是 table、text 或 image")
        kind = item["kind"]
        extra = {"table": {"columns", "rows"}, "text": {"text"}, "image": {"file", "alt"}}[kind]
        require(not set(item) - {"id", "title", "kind"} - extra, "材料字段无效")
        require(isinstance(item.get("id"), str) and re.fullmatch(QUIZ_ID, item["id"]) and item["id"] not in ids, "材料编号无效或重复")
        ids.add(item["id"])
        result = {"id": item["id"], "title": _text(item.get("title", ""), 128, "材料标题无效", empty=True), "kind": kind}
        if kind == "table":
            columns, rows = item.get("columns"), item.get("rows")
            require(isinstance(columns, list) and 1 <= len(columns) <= 12, "表格需要 1–12 列")
            require(isinstance(rows, list) and 1 <= len(rows) <= 100 and
                    all(isinstance(row, list) and len(row) == len(columns) for row in rows), "表格需要 1–100 行，且每行列数与表头一致")
            result.update(columns=[_text(column, 200, "表头无效", empty=True) for column in columns],
                          rows=[[_cell(cell) for cell in row] for row in rows])
        elif kind == "text":
            result["text"] = _text(item.get("text"), 20000, "文本材料无效")
        else:
            file = item.get("file")
            require(isinstance(file, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.(png|jpg|jpeg|webp)", file), "图片材料需引用 media/ 下的 PNG、JPEG 或 WebP")
            result.update(file=file, alt=_text(item.get("alt", ""), 200, "图片说明无效", empty=True))
        materials.append(result)
    questions, seen = [], set(ids)
    raw = value.get("questions")
    require(isinstance(raw, list) and 1 <= len(raw) <= 50, "作答卡需要 1–50 道小题")
    for item in raw:
        require(isinstance(item, dict) and item.get("kind") in QUIZ_KINDS, "小题类型必须是 single、multiple、number 或 order")
        kind = item["kind"]
        allowed = {"id", "kind", "prompt", "points", "materials"} | ({"unit"} if kind == "number" else {"options"})
        require(not set(item) - allowed, "小题字段无效")
        require(isinstance(item.get("id"), str) and re.fullmatch(QUIZ_ID, item["id"]) and item["id"] not in seen, "小题编号无效或与其他编号重复")
        seen.add(item["id"])
        require(type(item.get("points")) is int and 1 <= item["points"] <= 100, "小题分值必须在 1–100 之间")
        refs = item.get("materials", [])
        require(isinstance(refs, list) and len(set(refs)) == len(refs) and all(ref in ids for ref in refs), "小题引用了不存在的材料")
        result = {"id": item["id"], "kind": kind, "prompt": _text(item.get("prompt"), 4000, "小题题干无效"),
                  "points": item["points"], "materials": refs}
        if kind == "number":
            result["unit"] = _text(item.get("unit", ""), 32, "数值单位无效", empty=True)
        else:
            options = item.get("options")
            require(isinstance(options, list) and 2 <= len(options) <= 12, "选择和排序题需要 2–12 个选项")
            result["options"] = [_text(option, 500, "选项无效") for option in options]
        questions.append(result)
    return {"materials": materials, "questions": questions}


def _index(value, count):
    return type(value) is int and 0 <= value < count


def quiz_key_input(quiz, value):
    """Validate the private answer key against the public card; never exposed to students."""
    questions = {question["id"]: question for question in quiz["questions"]}
    require(isinstance(value, dict) and set(value) == set(questions), "answers.json 必须恰好覆盖每道小题")
    result = {}
    for qid, entry in value.items():
        question = questions[qid]
        kind, count = question["kind"], len(question.get("options", []))
        require(isinstance(entry, dict) and "answer" in entry, "答案格式无效：" + qid)
        answer = entry["answer"]
        if kind == "single":
            require(set(entry) == {"answer"} and _index(answer, count), "单选答案必须是选项下标：" + qid)
            result[qid] = {"answer": answer}
        elif kind == "multiple":
            require(not set(entry) - {"answer", "scoring"} and isinstance(answer, list) and answer and
                    len(set(answer)) == len(answer) and all(_index(option, count) for option in answer), "多选答案必须是选项下标列表：" + qid)
            scoring = entry.get("scoring", "all")
            require(scoring in ("all", "partial"), "多选计分方式必须是 all 或 partial：" + qid)
            result[qid] = {"answer": sorted(answer), "scoring": scoring}
        elif kind == "number":
            require(not set(entry) - {"answer", "tolerance", "relative"}, "数值答案字段无效：" + qid)
            numbers = [answer, entry.get("tolerance", 0), entry.get("relative", 0)]
            require(all(type(number) in (int, float) and math.isfinite(number) for number in numbers) and
                    numbers[1] >= 0 and numbers[2] >= 0, "数值答案和容差必须是有限数：" + qid)
            result[qid] = {"answer": numbers[0], "tolerance": numbers[1], "relative": numbers[2]}
        else:
            require(set(entry) == {"answer"} and isinstance(answer, list) and sorted(answer) == list(range(count)) and
                    all(type(option) is int for option in answer), "排序答案必须是全部选项下标的排列：" + qid)
            result[qid] = {"answer": answer}
    return result


def media_input(files, quiz):
    """Inline the referenced quiz images as data URIs after checking their real content type."""
    used = {item["file"] for item in quiz["materials"] if item["kind"] == "image"}
    require(set(files) == used, "media/ 中的图片必须与图片材料一一对应")
    require(len(files) <= MAX_MEDIA_FILES and sum(map(len, files.values())) <= MAX_MEDIA_TOTAL, "作答卡图片最多 8 张、总计 1 MiB")
    result = {}
    for name, content in sorted(files.items()):
        mime, magics = MEDIA_TYPES[name.rsplit(".", 1)[1].lower()]
        require(len(content) <= MAX_MEDIA_FILE and content.startswith(magics) and
                (mime != "image/webp" or content[8:12] == b"WEBP"), "图片内容与扩展名不符或超过 400 KiB：" + name)
        result[name] = "data:" + mime + ";base64," + base64.b64encode(content).decode("ascii")
    return result


def metadata_input(value):
    require(isinstance(value, dict), "problem.json 必须为对象")
    require(not set(value) - {"format", "version", "source_id", "title", "type", "metric", "points", "statement", "evaluation", "quiz"},
            "problem.json 存在未知字段")
    require(value.get("format") == FORMAT and type(value.get("version")) is int and value["version"] == 1,
            "请选择 xju-ai-problem v1 题包；普通 OJ 题包请使用普通题目导入")
    title = value.get("title")
    require(isinstance(title, str) and 1 <= len(title.strip()) <= 128 and "\x00" not in title, "题目标题无效")
    require(value.get("type") in TYPES, "题型必须是 logic、model、challenge 或 quiz")
    metric = value.get("metric", "Score")
    points = value.get("points", 100)
    require(isinstance(metric, str) and 1 <= len(metric) <= 64 and "\x00" not in metric, "指标名称无效")
    require(type(points) is int and 1 <= points <= 10000, "分值必须在 1–10000 之间")
    source_id = value.get("source_id", "")
    require(isinstance(source_id, str) and (not source_id or re.fullmatch(r"[A-Za-z0-9_-]{1,32}", source_id)), "来源编号无效")
    result = {"format": FORMAT, "version": 1, "source_id": source_id, "title": title.strip(), "type": value["type"],
              "metric": metric, "points": points, "statement": statement_input(value.get("statement")),
              "evaluation": evaluation_input(value.get("evaluation", {}))}
    if value["type"] == "quiz":
        require("quiz" in value, "模型理解题需要在 problem.json 中提供 quiz 作答卡")
        result["quiz"] = quiz_input(value["quiz"])
        require(not {"private_column", "accuracy_column"} & set(result["evaluation"]), "模型理解题只有一个得分列")
    else:
        require("quiz" not in value and "max_attempts" not in result["evaluation"], "只有模型理解题可以配置 quiz 和 max_attempts")
    return result


def notebook_cells(raw):
    require(len(raw) <= 2 * 1024 * 1024, "starter.ipynb 超过 2 MiB")
    notebook = read_json(raw)
    require(isinstance(notebook, dict) and notebook.get("nbformat") == 4 and isinstance(notebook.get("cells"), list),
            "starter.ipynb 必须为 Notebook v4")
    cells = []
    for cell in notebook["cells"]:
        require(isinstance(cell, dict) and cell.get("cell_type") in ("code", "markdown", "raw"), "Notebook 单元格格式无效")
        source = cell.get("source", "")
        if isinstance(source, list):
            require(all(isinstance(line, str) for line in source), "Notebook 源码格式无效")
            source = "".join(source)
        require(isinstance(source, str) and "\x00" not in source, "Notebook 源码格式无效")
        if cell["cell_type"] == "code":
            cells.append(source)
    require(1 <= len(cells) <= 64 and sum(len(c.encode()) for c in cells) <= 512 * 1024, "Notebook 需包含 1–64 格代码，总计不超过 512 KiB")
    return cells


def _archive(raw, budget):
    require(len(raw) <= MAX_UPLOAD, "ZIP 文件超过 16 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files, seen, directories = {}, set(), set()
            members = archive.infolist()
            budget[1] += len(members)
            require(budget[1] <= MAX_MEMBERS, "题包文件数量超过上限")
            for member in members:
                name = member.filename
                path = PurePosixPath(name)
                require(name and member.orig_filename == name and len(name) <= 240 and "\\" not in name and ":" not in name and
                        "\x00" not in name and not path.is_absolute() and
                        not any(part in ("", ".", "..") for part in name.rstrip("/").split("/")), "ZIP 包含不安全路径")
                require(name.casefold().rstrip("/") not in seen, "ZIP 包含重复或大小写冲突的路径")
                seen.add(name.casefold().rstrip("/"))
                parents = {str(parent).casefold() for parent in path.parents if str(parent) != "."}
                require(not parents.intersection(key.casefold() for key in files), "ZIP 文件与目录路径冲突")
                require(member.is_dir() or name.casefold() not in directories, "ZIP 文件与目录路径冲突")
                directories.update(parents)
                if member.is_dir():
                    directories.add(name.casefold().rstrip("/"))
                mode = stat.S_IFMT(member.external_attr >> 16)
                require(mode in (0, stat.S_IFDIR if member.is_dir() else stat.S_IFREG), "ZIP 不允许链接或特殊文件")
                require(not member.flag_bits & 1 and member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "ZIP 不允许加密或不支持的压缩方式")
                budget[0] += member.file_size
                require(member.file_size <= MAX_MEMBER and budget[0] <= MAX_EXPANDED, "ZIP 解压大小超过上限")
                if not member.is_dir():
                    content = archive.read(member)
                    require(len(content) == member.file_size, "ZIP 文件长度无效")
                    files[name] = content
            return files
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error) as exc:
        raise PackageError("ZIP 文件损坏或无法读取") from exc


def _problem(files, name):
    require("problem.json" in files, "单题 ZIP 需包含 problem.json")
    require(len(files["problem.json"]) <= 512 * 1024, "problem.json 超过 512 KiB")
    metadata = metadata_input(read_json(files["problem.json"]))
    quiz = metadata["type"] == "quiz"
    require(quiz != ("starter.ipynb" in files), "模型理解题不使用 starter.ipynb，其他题型必须提供 starter.ipynb")
    require(metadata["type"] != "challenge" or "private_column" in metadata["evaluation"], "数据挑战需配置 private_column")
    public, assets, media = {}, {kind: {} for kind in ASSET_FOLDERS}, {}
    for path, content in files.items():
        if path in ("problem.json", "starter.ipynb"):
            continue
        if quiz and path.startswith("media/"):
            filename = path[6:]
            require(re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.(png|jpg|jpeg|webp)", filename), "media/ 仅支持 PNG、JPEG、WebP 图片")
            media[filename] = content
            continue
        if path.startswith("data/"):
            filename = path[5:]
            require(re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.csv", filename), "公开数据仅支持 data/ 下的 CSV 文件")
            try:
                public[filename] = content.decode("utf-8-sig")
            except UnicodeError as exc:
                raise PackageError("公开 CSV 必须使用 UTF-8") from exc
            require("\x00" not in public[filename], "公开 CSV 包含无效字符")
            continue
        matched = False
        for kind, folder in ASSET_FOLDERS.items():
            prefix = "evaluation/" + folder + "/"
            if path.startswith(prefix):
                relative = path[len(prefix):]
                require(re.fullmatch(r"[A-Za-z0-9_./-]+", relative) and relative != "metadata.yaml", "评测文件路径无效；metadata.yaml 由平台生成")
                assets[kind][relative] = content
                matched = True
                break
        require(matched, "题包包含布局之外的文件")
    require(len(public) <= 16 and len(json.dumps(public).encode()) <= 1024 * 1024, "公开数据最多 16 个 CSV，总计不超过 1 MiB")
    if quiz:
        # The OJ grades the card itself: only the private answer key is an evaluation asset.
        require(set(assets["reference_data"]) == {"answers.json"} and
                not any(assets[kind] for kind in ASSET_FOLDERS if kind != "reference_data"),
                "模型理解题的评测目录只能包含 evaluation/reference/answers.json")
        key = quiz_key_input(metadata["quiz"], read_json(assets["reference_data"]["answers.json"]))
        return {"name": name, "metadata": metadata, "cells": [], "public_files": public,
                "media": media_input(media, metadata["quiz"]), "assets": assets, "quiz_key": key,
                "asset_sha256": {"reference_data": hashlib.sha256(make_zip(assets["reference_data"], limit=MAX_EXPANDED)).hexdigest()}}
    require("program.py" in assets["scoring_program"], "缺少 evaluation/scoring/program.py")
    require(bool(assets["reference_data"]), "缺少 evaluation/reference/ 私有参考数据")
    # Each asset is unpacked independently by the existing compute sandbox.
    # Leave room for the platform-generated metadata.yaml in program bundles.
    require(all(len(values) <= 255 and sum(map(len, values.values())) <= 32 * 1024 * 1024 - 1024
                for values in assets.values()), "单类评测资产最多 255 个文件、32 MiB（预留 1 KiB）")
    if metadata["type"] != "challenge":
        require("program.py" in assets["ingestion_program"], "逻辑实现和模型定义需提供 evaluation/ingestion/program.py")
    else:
        require(not assets["ingestion_program"] and not assets["input_data"], "数据挑战直接评分 predictions.csv，无需 ingestion 和 input")
    cells = notebook_cells(files["starter.ipynb"])
    return {"name": name, "metadata": metadata, "cells": cells, "public_files": public, "assets": assets,
            "asset_sha256": {kind: hashlib.sha256(make_zip(values, limit=MAX_EXPANDED)).hexdigest()
                             for kind, values in assets.items() if values}}


def parse_package(raw):
    budget = [0, 0]
    files = _archive(raw, budget)
    if "problem.json" in files:
        return [_problem(files, "problem.zip")]
    require(1 <= len(files) <= MAX_PROBLEMS and all("/" not in name and name.lower().endswith(".zip") for name in files),
            "批量 ZIP 外层只允许放置 1–20 个单题 ZIP")
    def order(name):
        return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]
    problems = [_problem(_archive(files[name], budget), name) for name in sorted(files, key=order)]
    # Quiz batches are published by the OJ directly; code batches go through evaluation registration.
    require(len({item["metadata"]["type"] == "quiz" for item in problems}) == 1, "模型理解题与代码题需分别打包导入或导出")
    return problems


def make_zip(files, limit=MAX_UPLOAD):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(entry, content)
    value = stream.getvalue()
    require(len(value) <= limit, "导出题包超过 16 MiB，请减少选中的题目")
    return value


def export_problem(metadata, cells, public_files, assets, media=None):
    metadata = metadata_input(metadata)
    files = {"problem.json": json.dumps(metadata, ensure_ascii=False, indent=2)}
    if metadata["type"] == "quiz":
        files.update({"media/" + name: base64.b64decode(uri.split(",", 1)[1]) for name, uri in (media or {}).items()})
    else:
        notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}},
                    "cells": [{"id": "cell-" + str(i), "cell_type": "code", "metadata": {}, "source": [source],
                               "execution_count": None, "outputs": []} for i, source in enumerate(cells)]}
        files["starter.ipynb"] = json.dumps(notebook, ensure_ascii=False)
    files.update({"data/" + name: content for name, content in public_files.items()})
    for kind, content in assets.items():
        files.update({"evaluation/" + ASSET_FOLDERS[kind] + "/" + name: data for name, data in content.items()})
    value = make_zip(files)
    parse_package(value)
    return value
