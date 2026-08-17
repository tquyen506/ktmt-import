from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import zipfile
import os
import re
import unicodedata


app = FastAPI()


# =========================================================
# CHUẨN HÓA TIẾNG VIỆT
# =========================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text).lower()

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )

    text = text.replace("đ", "d")

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    return " ".join(text.split())


# =========================================================
# KIỂM TRA WORD
# =========================================================

def is_word_file(filename):

    name = filename.lower()

    return (
        name.endswith(".doc")
        or name.endswith(".docx")
    )


# =========================================================
# TÌM TẤT CẢ FILE WORD
# =========================================================

def find_word_files(tmp_dir):

    result = []

    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            if not is_word_file(filename):
                continue

            full_path = os.path.join(
                root,
                filename
            )

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
# CHẤM ĐIỂM FILE KTMT
# =========================================================

def score_ktmt(item):

    text = normalize_text(
        item["relative"]
    )

    score = 0

    if "lich ktmt" in text:
        score += 1000

    if "lich kiem tra" in text:
        score += 900

    if "ktmt" in text:
        score += 800

    if "kiem tra" in text:
        score += 700

    return score


# =========================================================
# CHẤM ĐIỂM FILE CÁN BỘ TRỰC
# =========================================================

def score_canbo(item):

    text = normalize_text(
        item["relative"]
    )

    score = 0

    if "lich cong tac tuan" in text:
        score += 1000

    if "lich cong tac" in text:
        score += 900

    if "cong tac tuan" in text:
        score += 800

    if "can bo truc" in text:
        score += 1000

    if "can bo" in text:
        score += 700

    if "truc" in text:
        score += 500

    return score


# =========================================================
# TÌM FILE KTMT
# =========================================================

def find_ktmt_file(word_files):

    if not word_files:
        return None

    scored = []

    for item in word_files:

        scored.append({
            **item,
            "score": score_ktmt(item)
        })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    if scored[0]["score"] > 0:
        return scored[0]

    return None


# =========================================================
# TÌM FILE CÁN BỘ TRỰC
# =========================================================

def find_canbo_file(word_files):

    if not word_files:
        return None

    scored = []

    for item in word_files:

        scored.append({
            **item,
            "score": score_canbo(item)
        })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    if scored[0]["score"] > 0:
        return scored[0]

    # -----------------------------------------------------
    # FALLBACK
    #
    # ZIP của bạn hiện có đúng 2 file Word:
    #
    # 1. Lịch công tác tuần...
    # 2. LỊCH KTMT...
    #
    # Nếu tên thay đổi thì lấy file Word còn lại
    # sau khi loại file KTMT.
    # -----------------------------------------------------

    ktmt = find_ktmt_file(word_files)

    if ktmt:

        for item in word_files:

            if item["path"] != ktmt["path"]:

                return item

    return None


# =========================================================
# TÌM FILE THEO KIND
# =========================================================

def find_target_file(word_files, kind):

    kind = normalize_text(kind)

    if kind == "ktmt":

        return find_ktmt_file(
            word_files
        )

    if kind == "canbo":

        return find_canbo_file(
            word_files
        )

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
# LIST ZIP
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
        "input.zip"
    )

    try:

        data = await file.read()

        with open(zip_path, "wb") as f:
            f.write(data)

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": "Không thể lưu ZIP",
                "detail": str(e)
            }
        )

    if not zipfile.is_zipfile(zip_path):

        return JSONResponse(
            status_code=400,
            content={
                "error": "File upload không phải ZIP"
            }
        )

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
                "error": "Không thể giải nén ZIP",
                "detail": str(e)
            }
        )

    word_files = find_word_files(
        tmp_dir
    )

    return {
        "zip": file.filename,
        "total_files": len(names),

        "word_files": [
            {
                "filename": x["filename"],
                "path": x["relative"]
            }
            for x in word_files
        ],

        "all_files": names
    }


# =========================================================
# EXTRACT
#
# /extract?kind=ktmt
#
# /extract?kind=canbo
#
# QUAN TRỌNG:
# File trả về luôn có tên ASCII:
#
# ktmt.doc
# canbo.doc
#
# để tránh lỗi latin-1 với tên tiếng Việt.
# =========================================================

@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    kind: str = Query(
        default="ktmt"
    )
):

    tmp_dir = tempfile.mkdtemp()

    zip_path = os.path.join(
        tmp_dir,
        "input.zip"
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
                "error": "Không thể lưu ZIP",
                "detail": str(e),
                "kind": kind
            }
        )


    # =====================================================
    # 2. KIỂM TRA ZIP
    # =====================================================

    if not zipfile.is_zipfile(zip_path):

        return JSONResponse(
            status_code=400,
            content={
                "error": "File upload không phải ZIP",
                "kind": kind
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
                "error": "Không thể giải nén ZIP",
                "detail": str(e),
                "kind": kind
            }
        )


    # =====================================================
    # 4. TÌM WORD
    # =====================================================

    word_files = find_word_files(
        tmp_dir
    )

    if not word_files:

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm thấy file Word",
                "kind": kind
            }
        )


    # =====================================================
    # 5. CHỌN FILE
    # =====================================================

    target = find_target_file(
        word_files,
        kind
    )


    if target is None:

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm được file yêu cầu",
                "kind": kind,

                "word_files": [
                    {
                        "filename": x["filename"],
                        "path": x["relative"]
                    }
                    for x in word_files
                ]
            }
        )


    # =====================================================
    # 6. CHỌN TÊN ASCII CHO FILE TRẢ VỀ
    # =====================================================

    if normalize_text(kind) == "ktmt":

        output_name = "ktmt.doc"

    else:

        output_name = "canbo.doc"


    # =====================================================
    # 7. LOG SERVER
    # =====================================================

    print(
        "======================================"
    )

    print(
        "ZIP:",
        file.filename
    )

    print(
        "KIND:",
        kind
    )

    print(
        "SELECTED:",
        target["filename"]
    )

    print(
        "OUTPUT:",
        output_name
    )

    print(
        "======================================"
    )


    # =====================================================
    # 8. TRẢ FILE
    #
    # KHÔNG gửi filename tiếng Việt.
    # Đây chính là phần sửa lỗi latin-1.
    # =====================================================

    try:

        return FileResponse(
            path=target["path"],
            filename=output_name,
            media_type="application/octet-stream"
        )

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": "Không thể trả file",
                "detail": str(e),
                "kind": kind
            }
        )
