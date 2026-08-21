import os
import io
import re
import base64
import zipfile
import unicodedata
from flask import Flask, request, jsonify


app = Flask(__name__)


# ============================================================
# CONFIG
# ============================================================

MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(text):
    """
    Chuyển:
        "Lịch cán bộ trực"
    thành:
        "lich can bo truc"

    Giúp nhận diện tên file không phụ thuộc dấu tiếng Việt.
    """

    if text is None:
        return ""

    text = str(text).strip().lower()

    text = unicodedata.normalize(
        "NFD",
        text
    )

    text = "".join(
        c
        for c in text
        if unicodedata.category(c) != "Mn"
    )

    return text


# ============================================================
# DETECT FILE TYPE
# ============================================================

def detect_file_kind(filename):
    """
    Phân loại file thành:
        ktmt
        canbo
        unknown
    """

    name = normalize_text(filename)

    # --------------------------------------------------------
    # CÁN BỘ TRỰC
    # --------------------------------------------------------

    canbo_keywords = [
        "can bo truc",
        "canbotruc",
        "truc can bo",
        "lich can bo",
        "lich truc",
        "lichtruc",
        "truc ban",
        "trucban",
        "chi huy",
        "canbo",
    ]

    for keyword in canbo_keywords:
        if keyword in name:
            return "canbo"


    # --------------------------------------------------------
    # KTMT
    # --------------------------------------------------------

    ktmt_keywords = [
        "ktmt",
        "kiem tra",
        "kiemtra",
        "muc tieu",
        "muctieu",
        "lich ktmt",
        "lich kiem tra",
    ]

    for keyword in ktmt_keywords:
        if keyword in name:
            return "ktmt"


    return "unknown"


# ============================================================
# DETECT DATE RANGE FROM FILE NAME
# ============================================================

def extract_date_range(filename):
    """
    Cố gắng lấy khoảng ngày từ tên file.

    Ví dụ:
        Lịch trực và ktmt từ 24.8 đến 06.9.2026.docx

    trả về:
        {
            "start": "24.8",
            "end": "06.9",
            "year": "2026"
        }

    Nếu không tìm thấy thì trả về None.
    """

    name = normalize_text(filename)

    patterns = [

        # 24.8 đến 06.9.2026
        r"(\d{1,2})[./-](\d{1,2})\s*(?:den|-|to)\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})",

        # 24.8 - 06.9.2026
        r"(\d{1,2})[./-](\d{1,2})\s*[-]\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            name
        )

        if match:

            return {
                "start_day": match.group(1),
                "start_month": match.group(2),
                "end_day": match.group(3),
                "end_month": match.group(4),
                "year": match.group(5)
            }


    return None


# ============================================================
# CHECK WORD FILE
# ============================================================

def is_word_file(filename):

    name = filename.lower()

    return (
        name.endswith(".doc") or
        name.endswith(".docx")
    )


# ============================================================
# READ ZIP
# ============================================================

def read_zip(zip_bytes):

    result = []

    with zipfile.ZipFile(
        io.BytesIO(zip_bytes)
    ) as z:

        for info in z.infolist():

            # ------------------------------------------------
            # Bỏ folder
            # ------------------------------------------------

            if info.is_dir():
                continue


            filename = info.filename


            # ------------------------------------------------
            # Chỉ lấy Word
            # ------------------------------------------------

            if not is_word_file(filename):
                continue


            # ------------------------------------------------
            # Đọc file
            # ------------------------------------------------

            data = z.read(
                info.filename
            )


            kind = detect_file_kind(
                filename
            )


            date_range = extract_date_range(
                filename
            )


            encoded = base64.b64encode(
                data
            ).decode("utf-8")


            result.append({

                "filename": os.path.basename(
                    filename
                ),

                "path": filename,

                "kind": kind,

                "size": len(data),

                "date_range": date_range,

                "data": encoded

            })


    return result


# ============================================================
# SORT FILES
# ============================================================

def sort_files(files):

    def sort_key(item):

        date_range = item.get(
            "date_range"
        )

        if not date_range:
            return (
                9999,
                99,
                99,
                item.get(
                    "filename",
                    ""
                )
            )


        try:

            year = int(
                date_range["year"]
            )

            month = int(
                date_range["start_month"]
            )

            day = int(
                date_range["start_day"]
            )

            return (
                year,
                month,
                day,
                item.get(
                    "filename",
                    ""
                )
            )

        except Exception:

            return (
                9999,
                99,
                99,
                item.get(
                    "filename",
                    ""
                )
            )


    return sorted(
        files,
        key=sort_key
    )


# ============================================================
# GROUP FILES INTO PAIRS
# ============================================================

def group_into_pairs(files):

    ktmt = [
        x
        for x in files
        if x["kind"] == "ktmt"
    ]

    canbo = [
        x
        for x in files
        if x["kind"] == "canbo"
    ]


    ktmt = sort_files(
        ktmt
    )

    canbo = sort_files(
        canbo
    )


    pairs = []


    # --------------------------------------------------------
    # Ghép theo khoảng ngày
    # --------------------------------------------------------

    used_canbo = set()


    for ktmt_file in ktmt:

        matched_index = None


        ktmt_range = ktmt_file.get(
            "date_range"
        )


        for index, canbo_file in enumerate(
            canbo
        ):

            if index in used_canbo:
                continue


            canbo_range = canbo_file.get(
                "date_range"
            )


            if (
                ktmt_range is not None and
                canbo_range is not None
            ):

                if (
                    ktmt_range["start_day"] ==
                    canbo_range["start_day"]
                    and
                    ktmt_range["start_month"] ==
                    canbo_range["start_month"]
                    and
                    ktmt_range["end_day"] ==
                    canbo_range["end_day"]
                    and
                    ktmt_range["end_month"] ==
                    canbo_range["end_month"]
                    and
                    ktmt_range["year"] ==
                    canbo_range["year"]
                ):

                    matched_index = index
                    break


        # ----------------------------------------------------
        # Nếu tìm được cặp
        # ----------------------------------------------------

        if matched_index is not None:

            canbo_file = canbo[
                matched_index
            ]

            used_canbo.add(
                matched_index
            )

        else:

            canbo_file = None


        pairs.append({

            "ktmt": ktmt_file,

            "canbo": canbo_file

        })


    # --------------------------------------------------------
    # Những file cán bộ trực chưa ghép
    # --------------------------------------------------------

    for index, canbo_file in enumerate(
        canbo
    ):

        if index not in used_canbo:

            pairs.append({

                "ktmt": None,

                "canbo": canbo_file

            })


    return pairs


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status": "ok",

        "service": "ktmt-import",

        "message": "Render đang hoạt động."

    })


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({

        "status": "ok",

        "service": "ktmt-import",

        "endpoints": [

            "GET /health",

            "POST /extract-all"

        ]

    })


# ============================================================
# EXTRACT ALL
# ============================================================

@app.route(
    "/extract-all",
    methods=["POST"]
)
def extract_all():

    try:

        # ====================================================
        # KIỂM TRA FILE
        # ====================================================

        if "file" not in request.files:

            return jsonify({

                "success": False,

                "error":
                    "Không tìm thấy file ZIP trong request."

            }), 400


        uploaded_file = request.files[
            "file"
        ]


        if not uploaded_file:

            return jsonify({

                "success": False,

                "error":
                    "File upload không hợp lệ."

            }), 400


        filename = (
            uploaded_file.filename
            or
            "upload.zip"
        )


        # ====================================================
        # ĐỌC ZIP
        # ====================================================

        zip_bytes =
            uploaded_file.read()


        if not zip_bytes:

            return jsonify({

                "success": False,

                "error":
                    "File ZIP rỗng."

            }), 400


        if len(zip_bytes) > MAX_FILE_SIZE:

            return jsonify({

                "success": False,

                "error":
                    "File ZIP vượt quá "
                    + str(MAX_FILE_SIZE_MB)
                    + " MB."

            }), 413


        # ====================================================
        # KIỂM TRA ZIP
        # ====================================================

        try:

            if not zipfile.is_zipfile(
                io.BytesIO(zip_bytes)
            ):

                return jsonify({

                    "success": False,

                    "error":
                        "File gửi lên không phải ZIP hợp lệ."

                }), 400

        except Exception:

            return jsonify({

                "success": False,

                "error":
                    "Không thể kiểm tra ZIP."

            }), 400


        # ====================================================
        # ĐỌC TOÀN BỘ WORD
        # ====================================================

        files = read_zip(
            zip_bytes
        )


        if len(files) == 0:

            return jsonify({

                "success": False,

                "error":
                    "Không tìm thấy file Word nào trong ZIP.",

                "zip_filename":
                    filename

            }), 400


        # ====================================================
        # SẮP XẾP
        # ====================================================

        files = sort_files(
            files
        )


        # ====================================================
        # PHÂN LOẠI
        # ====================================================

        ktmt_files = [

            x
            for x in files
            if x["kind"] == "ktmt"

        ]


        canbo_files = [

            x
            for x in files
            if x["kind"] == "canbo"

        ]


        unknown_files = [

            x
            for x in files
            if x["kind"] == "unknown"

        ]


        # ====================================================
        # GHÉP CẶP
        # ====================================================

        pairs = group_into_pairs(
            files
        )


        # ====================================================
        # TẠO RESPONSE
        # ====================================================

        response_pairs = []


        for index, pair in enumerate(
            pairs,
            start=1
        ):

            ktmt_file = pair.get(
                "ktmt"
            )

            canbo_file = pair.get(
                "canbo"
            )


            response_pairs.append({

                "pair_index":
                    index,

                "date_range":
                    (
                        ktmt_file.get(
                            "date_range"
                        )
                        if ktmt_file
                        else
                        (
                            canbo_file.get(
                                "date_range"
                            )
                            if canbo_file
                            else None
                        )
                    ),

                "ktmt":
                    ktmt_file,

                "canbo":
                    canbo_file

            })


        # ====================================================
        # LOG
        # ====================================================

        print(
            "======================================"
        )

        print(
            "ZIP: " +
            filename
        )

        print(
            "Tổng file Word: " +
            str(len(files))
        )

        print(
            "KTMT: " +
            str(len(ktmt_files))
        )

        print(
            "Cán bộ trực: " +
            str(len(canbo_files))
        )

        print(
            "Không xác định: " +
            str(len(unknown_files))
        )

        print(
            "Số cặp: " +
            str(len(response_pairs))
        )

        print(
            "======================================"
        )


        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "success": True,

            "zip_filename":
                filename,

            "total_word_files":
                len(files),

            "total_ktmt":
                len(ktmt_files),

            "total_canbo":
                len(canbo_files),

            "total_unknown":
                len(unknown_files),

            "total_pairs":
                len(response_pairs),

            "files":
                files,

            "pairs":
                response_pairs,

            "unknown_files":
                unknown_files

        })


    except zipfile.BadZipFile:

        return jsonify({

            "success": False,

            "error":
                "ZIP bị lỗi hoặc không thể giải nén."

        }), 400


    except Exception as e:

        print(
            "ERROR:",
            repr(e)
        )


        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )


    app.run(
        host="0.0.0.0",
        port=port
    )
