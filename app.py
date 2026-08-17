from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse

import tempfile
import zipfile
import os
import re
import unicodedata


app = FastAPI()


# =========================================================
# CHUẨN HÓA CHUỖI
# =========================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text).lower()

    # Bỏ dấu tiếng Việt
    text = unicodedata.normalize("NFD", text)

    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )

    # đ -> d
    text = text.replace("đ", "d")

    # Ký tự đặc biệt -> khoảng trắng
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    return " ".join(
        text.split()
    )


# =========================================================
# KIỂM TRA FILE WORD
# =========================================================

def is_word_file(filename):

    name = filename.lower()

    return (
        name.endswith(".doc")
        or name.endswith(".docx")
    )


# =========================================================
# ĐIỂM FILE LỊCH KIỂM TRA
# =========================================================

def score_ktmt(filename):

    text = normalize_text(filename)

    score = 0

    keywords = {

        "lich ktmt": 300,

        "lich kiem tra": 300,

        "ktmt": 250,

        "kiem tra": 200,

        "muc tieu": 100,

        "lich": 20,
    }

    for keyword, value in keywords.items():

        if keyword in text:
            score += value

    return score


# =========================================================
# ĐIỂM FILE CÁN BỘ TRỰC
# =========================================================

def score_canbo(filename):

    text = normalize_text(filename)

    score = 0

    keywords = {

        # Tên file thực tế của bạn
        "lich cong tac tuan": 500,

        "lich cong tac": 400,

        "cong tac tuan": 350,

        # Các trường hợp khác
        "can bo truc": 500,

        "can bo": 300,

        "canbotruc": 500,

        "lich truc": 400,

        "lich can bo truc": 500,

        "lich can bo": 400,

        "bo tri truc": 300,

        "truc ban": 150,

        "truc ch": 150,

        "truc b1": 150,

        "truc b2": 50,

        "truc b3": 50,

        "truc": 100,
    }

    for keyword, value in keywords.items():

        if keyword in text:
            score += value

    return score


# =========================================================
# TÌM TẤT CẢ FILE WORD TRONG ZIP
# =========================================================

def find_word_files(tmp_dir):

    result = []

    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            full_path = os.path.join(
                root,
                filename
            )

            if not is_word_file(filename):
                continue

            relative_path = os.path.relpath(
                full_path,
                tmp_dir
            )

            result.append({

                "filename": filename,

                "path": full_path,

                "relative": relative_path
            })

    return result


# =========================================================
# TÌM FILE LỊCH KIỂM TRA
# =========================================================

def find_ktmt_file(word_files):

    if not word_files:
        return None

    scored = []

    for item in word_files:

        # Chấm cả đường dẫn + tên file
        text = item["relative"]

        score = score_ktmt(text)

        scored.append({

            **item,

            "score": score
        })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # Có file chứa từ khóa KTMT
    if scored[0]["score"] > 0:

        return scored[0]

    # -----------------------------------------------------
    # FALLBACK
    #
    # Nếu không nhận ra tên file,
    # lấy file Word không phải cán bộ trực.
    # -----------------------------------------------------

    for item in word_files:

        if score_canbo(
            item["relative"]
        ) == 0:

            return item

    return None


# =========================================================
# TÌM FILE CÁN BỘ TRỰC
# =========================================================

def find_canbo_file(word_files):

    if not word_files:
        return None

    scored = []

    for item in word_files:

        text = item["relative"]

        score = score_canbo(text)

        scored.append({

            **item,

            "score": score
        })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # -----------------------------------------------------
    # ƯU TIÊN FILE CÓ TỪ KHÓA
    # -----------------------------------------------------

    if scored[0]["score"] > 0:

        return scored[0]


    # -----------------------------------------------------
    # FALLBACK
    #
    # ZIP của bạn hiện có đúng:
    #
    # 1. lịch công tác tuần....doc
    # 2. LỊCH KTMT....doc
    #
    # Nếu không nhận diện được tên,
    # chọn file còn lại sau khi loại KTMT.
    # -----------------------------------------------------

    ktmt = find_ktmt_file(
        word_files
    )

    if ktmt:

        for item in word_files:

            if item["path"] != ktmt["path"]:

                return {

                    **item,

                    "score": 0,

                    "fallback": True
                }

    return None


# =========================================================
# TRANG CHỦ
# =========================================================

@app.get("/")
def home():

    return {

        "status": "ok",

        "service": "KTMT Import",

        "message": "KTMT Import service is running"
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {

        "status": "running"
    }


# =========================================================
# LIST
#
# Dùng để kiểm tra ZIP có những file gì
# =========================================================

@app.post("/list")
async def list_zip(
    file: UploadFile = File(...)
):

    tmp_dir = tempfile.mkdtemp()

    zip_path = os.path.join(
        tmp_dir,
        file.filename
    )

    # -----------------------------------------------------
    # LƯU ZIP
    # -----------------------------------------------------

    try:

        data = await file.read()

        with open(
            zip_path,
            "wb"
        ) as f:

            f.write(data)

    except Exception as e:

        return JSONResponse(

            status_code=500,

            content={

                "error": "Không thể lưu file ZIP",

                "detail": str(e)
            }
        )


    # -----------------------------------------------------
    # KIỂM TRA ZIP
    # -----------------------------------------------------

    if not zipfile.is_zipfile(
        zip_path
    ):

        return JSONResponse(

            status_code=400,

            content={

                "error":
                    "File upload không phải ZIP"
            }
        )


    # -----------------------------------------------------
    # GIẢI NÉN
    # -----------------------------------------------------

    try:

        with zipfile.ZipFile(
            zip_path,
            "r"
        ) as z:

            names = z.namelist()

            z.extractall(
                tmp_dir
            )

    except Exception as e:

        return JSONResponse(

            status_code=500,

            content={

                "error":
                    "Không thể giải nén ZIP",

                "detail":
                    str(e)
            }
        )


    # -----------------------------------------------------
    # TÌM FILE WORD
    # -----------------------------------------------------

    word_files = find_word_files(
        tmp_dir
    )


    # -----------------------------------------------------
    # TRẢ THÔNG TIN DEBUG
    # -----------------------------------------------------

    return {

        "zip": file.filename,

        "total_files": len(names),

        "word_files": [

            {

                "filename":
                    x["filename"],

                "path":
                    x["relative"],

                "ktmt_score":
                    score_ktmt(
                        x["relative"]
                    ),

                "canbo_score":
                    score_canbo(
                        x["relative"]
                    )
            }

            for x in word_files
        ],

        "all_files": names
    }


# =========================================================
# EXTRACT
#
# /extract?kind=ktmt
# /extract?kind=canbo
#
# =========================================================

@app.post("/extract")
async def extract(

    file: UploadFile = File(...),

    kind: str = "ktmt"
):

    tmp_dir = tempfile.mkdtemp()

    zip_path = os.path.join(

        tmp_dir,

        file.filename
    )


    # =====================================================
    # 1. LƯU ZIP
    # =====================================================

    try:

        data = await file.read()

        with open(
            zip_path,
            "wb"
        ) as f:

            f.write(data)

    except Exception as e:

        return JSONResponse(

            status_code=500,

            content={

                "error":
                    "Không thể lưu file ZIP",

                "detail":
                    str(e)
            }
        )


    # =====================================================
    # 2. KIỂM TRA ZIP
    # =====================================================

    if not zipfile.is_zipfile(
        zip_path
    ):

        return JSONResponse(

            status_code=400,

            content={

                "error":
                    "File upload không phải ZIP"
            }
        )


    # =====================================================
    # 3. GIẢI NÉN
    # =====================================================

    try:

        with zipfile.ZipFile(
            zip_path,
            "r"
        ) as z:

            z.extractall(
                tmp_dir
            )

    except Exception as e:

        return JSONResponse(

            status_code=500,

            content={

                "error":
                    "Không thể giải nén ZIP",

                "detail":
                    str(e)
            }
        )


    # =====================================================
    # 4. TÌM FILE WORD
    # =====================================================

    word_files = find_word_files(
        tmp_dir
    )


    if not word_files:

        return JSONResponse(

            status_code=404,

            content={

                "error":
                    "Không tìm thấy file .doc hoặc .docx trong ZIP",

                "all_files":
                    os.listdir(tmp_dir)
            }
        )


    # =====================================================
    # 5. CHUẨN HÓA KIND
    # =====================================================

    kind = normalize_text(
        kind
    )


    # =====================================================
    # 6. CHỌN FILE
    # =====================================================

    # -----------------------------------------------------
    # CÁN BỘ TRỰC
    # -----------------------------------------------------

    if kind in [

        "canbo",

        "can bo",

        "can bo truc",

        "canbotruc",

        "truc",

        "lich truc",

        "lich can bo",

        "lich can bo truc",

        "lich cong tac",

        "lich cong tac tuan",

        "cong tac",

        "cong tac tuan"
    ]:

        target = find_canbo_file(
            word_files
        )

        selected_type = (
            "CAN BO TRUC"
        )


    # -----------------------------------------------------
    # LỊCH KIỂM TRA
    # -----------------------------------------------------

    elif kind in [

        "ktmt",

        "lich ktmt",

        "kiem tra",

        "lich kiem tra"
    ]:

        target = find_ktmt_file(
            word_files
        )

        selected_type = (
            "LICH KIEM TRA"
        )


    # -----------------------------------------------------
    # KIND KHÔNG HỢP LỆ
    # -----------------------------------------------------

    else:

        return JSONResponse(

            status_code=400,

            content={

                "error":
                    "kind không hợp lệ",

                "kind":
                    kind,

                "allowed": [

                    "ktmt",

                    "canbo"
                ],

                "word_files": [

                    {

                        "filename":
                            x["filename"],

                        "path":
                            x["relative"]
                    }

                    for x in word_files
                ]
            }
        )


    # =====================================================
    # 7. KHÔNG TÌM ĐƯỢC FILE
    # =====================================================

    if target is None:

        return JSONResponse(

            status_code=404,

            content={

                "error":
                    "Không tìm được file yêu cầu",

                "kind":
                    kind,

                "word_files": [

                    {

                        "filename":
                            x["filename"],

                        "path":
                            x["relative"],

                        "ktmt_score":
                            score_ktmt(
                                x["relative"]
                            ),

                        "canbo_score":
                            score_canbo(
                                x["relative"]
                            )
                    }

                    for x in word_files
                ]
            }
        )


    # =====================================================
    # 8. TRẢ FILE WORD
    # =====================================================

    return FileResponse(

        path=target["path"],

        filename=target["filename"],

        media_type=
            "application/octet-stream",

        headers={

            "X-Selected-Type":
                selected_type,

            "X-Selected-File":
                target["filename"],

            "X-Selected-Score":
                str(
                    target.get(
                        "score",
                        0
                    )
                )
        }
    )
