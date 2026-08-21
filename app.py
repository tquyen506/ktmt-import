import os
import re
import io
import json
import zipfile
import tempfile
import shutil
from flask import Flask, request, jsonify

app = Flask(__name__)

# ============================================================
# CẤU HÌNH
# ============================================================

ALLOWED_EXTENSIONS = {
    ".doc",
    ".docx"
}

# ============================================================
# HÀM CHUẨN HÓA TÊN
# ============================================================

def normalize_text(text):
    if not text:
        return ""

    text = str(text)

    # chuẩn hóa Unicode
    import unicodedata
    text = unicodedata.normalize("NFC", text)

    # bỏ khoảng trắng thừa
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# NHẬN DIỆN LOẠI FILE
# ============================================================

def detect_kind(filename):

    name = normalize_text(
        os.path.basename(filename)
    ).lower()

    # --------------------------------------------
    # FILE KTMT
    # --------------------------------------------

    if (
        "ktmt" in name
        or "kiểm tra mục tiêu" in name
        or "kiem tra muc tieu" in name
    ):
        return "ktmt"

    # --------------------------------------------
    # FILE CÁN BỘ TRỰC
    # --------------------------------------------

    if (
        "lịch công tác" in name
        or "lich cong tac" in name
        or "cán bộ trực" in name
        or "can bo truc" in name
        or "lịch trực" in name
        or "lich truc" in name
    ):
        return "canbo"

    return "unknown"


# ============================================================
# LẤY KHOẢNG NGÀY TỪ TÊN FILE
#
# Hỗ trợ:
#
# 24.8 đến 30.8.2026
# 31.8 đến 06.9.2026
# Từ 24.8 đến ngày 30.8.2026
#
# ============================================================

def extract_date_range(filename):

    name = normalize_text(
        os.path.basename(filename)
    )

    # --------------------------------------------
    # Dạng:
    #
    # 24.8 đến 30.8.2026
    # --------------------------------------------

    pattern1 = re.search(
        r"(\d{1,2})[./-](\d{1,2})"
        r"\s*(?:đến|den|-|→|–)\s*"
        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})",
        name,
        re.IGNORECASE
    )

    if pattern1:

        d1 = int(pattern1.group(1))
        m1 = int(pattern1.group(2))

        d2 = int(pattern1.group(3))
        m2 = int(pattern1.group(4))

        year = int(pattern1.group(5))

        return {
            "from": f"{d1:02d}/{m1:02d}/{year}",
            "to": f"{d2:02d}/{m2:02d}/{year}"
        }

    # --------------------------------------------
    # Trường hợp:
    #
    # 24.8 đến 30.8
    #
    # nhưng năm nằm trước đó
    # --------------------------------------------

    pattern2 = re.search(
        r"(\d{1,2})[./-](\d{1,2})"
        r"\s*(?:đến|den|-|→|–)\s*"
        r"(\d{1,2})[./-](\d{1,2})"
        r"(?:[^\d]|$)",
        name,
        re.IGNORECASE
    )

    if pattern2:

        d1 = int(pattern2.group(1))
        m1 = int(pattern2.group(2))

        d2 = int(pattern2.group(3))
        m2 = int(pattern2.group(4))

        # Tìm năm gần cuối tên
        years = re.findall(
            r"(20\d{2})",
            name
        )

        if years:

            year = int(years[-1])

            return {
                "from": f"{d1:02d}/{m1:02d}/{year}",
                "to": f"{d2:02d}/{m2:02d}/{year}"
            }

    return None


# ============================================================
# KEY GHÉP CẶP
# ============================================================

def pair_key(date_range):

    if not date_range:
        return None

    return (
        date_range["from"]
        + "__"
        + date_range["to"]
    )


# ============================================================
# CHUYỂN ZIP THÀNH ZIP CHUẨN HÓA
#
# Render trả về một ZIP mới.
#
# Bên trong:
#
# manifest.json
# KTMT_...
# CANBO_...
#
# ============================================================

def build_normalized_zip(input_bytes):

    input_zip = zipfile.ZipFile(
        io.BytesIO(input_bytes),
        "r"
    )

    records = []

    for info in input_zip.infolist():

        if info.is_dir():
            continue

        original_name = info.filename

        # chỉ lấy file Word
        ext = os.path.splitext(
            original_name
        )[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            continue

        basename = os.path.basename(
            original_name
        )

        kind = detect_kind(
            basename
        )

        date_range = extract_date_range(
            basename
        )

        records.append({
            "original_name": basename,
            "kind": kind,
            "from": (
                date_range["from"]
                if date_range else None
            ),
            "to": (
                date_range["to"]
                if date_range else None
            ),
            "zip_name": original_name
        })

    # ========================================================
    # NHÓM THEO KHOẢNG NGÀY
    # ========================================================

    pairs = {}

    for record in records:

        if record["kind"] == "unknown":
            continue

        if not record["from"] or not record["to"]:
            continue

        key = (
            record["from"]
            + "__"
            + record["to"]
        )

        if key not in pairs:

            pairs[key] = {
                "from": record["from"],
                "to": record["to"],
                "ktmt": None,
                "canbo": None
            }

        if record["kind"] == "ktmt":
            pairs[key]["ktmt"] = record

        elif record["kind"] == "canbo":
            pairs[key]["canbo"] = record

    # ========================================================
    # SẮP XẾP THEO NGÀY
    # ========================================================

    def sort_key(item):

        from datetime import datetime

        try:
            return datetime.strptime(
                item["from"],
                "%d/%m/%Y"
            )
        except Exception:
            return datetime.max

    pair_list = list(
        pairs.values()
    )

    pair_list.sort(
        key=sort_key
    )

    # ========================================================
    # KIỂM TRA
    # ========================================================

    if len(pair_list) == 0:

        raise Exception(
            "Không tìm thấy cặp file Word hợp lệ."
        )

    # ========================================================
    # TẠO ZIP KẾT QUẢ
    # ========================================================

    output_buffer = io.BytesIO()

    with zipfile.ZipFile(
        output_buffer,
        "w",
        zipfile.ZIP_DEFLATED
    ) as output_zip:

        manifest_pairs = []

        for index, pair in enumerate(
            pair_list,
            start=1
        ):

            pair_info = {
                "index": index,
                "from": pair["from"],
                "to": pair["to"],
                "ktmt": None,
                "canbo": None
            }

            # --------------------------------------------
            # FILE KTMT
            # --------------------------------------------

            if pair["ktmt"]:

                source_name = (
                    pair["ktmt"]["zip_name"]
                )

                content = input_zip.read(
                    source_name
                )

                ext = os.path.splitext(
                    source_name
                )[1].lower()

                target_name = (
                    f"PAIR_{index:03d}_KTMT"
                    + ext
                )

                output_zip.writestr(
                    target_name,
                    content
                )

                pair_info["ktmt"] = {
                    "name": target_name,
                    "original_name": source_name
                }

            # --------------------------------------------
            # FILE CÁN BỘ
            # --------------------------------------------

            if pair["canbo"]:

                source_name = (
                    pair["canbo"]["zip_name"]
                )

                content = input_zip.read(
                    source_name
                )

                ext = os.path.splitext(
                    source_name
                )[1].lower()

                target_name = (
                    f"PAIR_{index:03d}_CANBO"
                    + ext
                )

                output_zip.writestr(
                    target_name,
                    content
                )

                pair_info["canbo"] = {
                    "name": target_name,
                    "original_name": source_name
                }

            manifest_pairs.append(
                pair_info
            )

        # --------------------------------------------
        # MANIFEST
        # --------------------------------------------

        manifest = {
            "success": True,
            "pairCount": len(
                manifest_pairs
            ),
            "pairs": manifest_pairs
        }

        output_zip.writestr(
            "manifest.json",
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2
            ).encode("utf-8")
        )

    output_buffer.seek(0)

    return (
        output_buffer.getvalue(),
        manifest
    )


# ============================================================
# API
# ============================================================

@app.route(
    "/extract-all",
    methods=["POST"]
)
def extract_all():

    try:

        if "file" not in request.files:

            return jsonify({
                "success": False,
                "error": "Không có file ZIP."
            }), 400

        uploaded_file = (
            request.files["file"]
        )

        filename = (
            uploaded_file.filename
            or ""
        )

        if not filename.lower().endswith(
            ".zip"
        ):

            return jsonify({
                "success": False,
                "error": "File gửi lên không phải ZIP."
            }), 400

        input_bytes = (
            uploaded_file.read()
        )

        if not input_bytes:

            return jsonify({
                "success": False,
                "error": "ZIP rỗng."
            }), 400

        result_zip, manifest = (
            build_normalized_zip(
                input_bytes
            )
        )

        # ====================================================
        # TRẢ VỀ ZIP
        # ====================================================

        from flask import Response

        response = Response(
            result_zip,
            status=200,
            mimetype="application/zip"
        )

        response.headers[
            "Content-Disposition"
        ] = (
            "attachment; "
            'filename="normalized_import.zip"'
        )

        response.headers[
            "X-Pair-Count"
        ] = str(
            manifest["pairCount"]
        )

        return response

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# API KIỂM TRA
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({
        "status": "ok"
    })


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
