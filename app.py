from fastapi import FastAPI, UploadFile, File
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

    text = re.sub(r"[^a-z0-9]+", " ", text)

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
# LẤY TẤT CẢ WORD TRONG ZIP
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
# CHẤM ĐIỂM FILE LỊCH KIỂM TRA
# =========================================================

def score_ktmt(item):

    text = normalize_text(
        item["relative"]
    )

    score = 0

    if "ktmt" in text:
        score += 100

    if "kiem tra" in text:
        score += 100

    if "lich kiem tra" in text:
        score += 150

    if "muc tieu" in text:
        score += 50

    if "lich" in text:
        score += 20

    return score


# =========================================================
# CHẤM ĐIỂM FILE CÁN BỘ TRỰC
# =========================================================

def score_canbo(item):

    text = normalize_text(
        item["relative"]
    )

    score = 0

    if "can bo truc" in text:
        score += 300

    if "can bo" in text:
        score += 200

    if "canbotruc" in text:
        score += 200

    if "lich truc" in text:
        score += 200

    if "bo tri truc" in text:
        score += 200

    if "truc ban" in text:
        score += 100

    if "truc ch" in text:
        score += 100

    if "truc b1" in text:
        score += 100

    if "truc" in text:
        score += 50

    return score


# =========================================================
# TÌM FILE LỊCH KIỂM TRA
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

    # Có từ khóa
    if scored[0]["score"] > 0:
        return scored[0]

    # Không nhận diện được bằng tên
    # nhưng nếu có 2 file thì chọn file đầu tiên
    if len(scored) >= 1:
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

    # -----------------------------------------------------
    # ƯU TIÊN FILE CÓ TÊN CÁN BỘ / TRỰC
    # -----------------------------------------------------

    if scored[0]["score"] > 0:
        return scored[0]

    # -----------------------------------------------------
    # FALLBACK:
    #
    # Nếu ZIP có đúng 2 file Word:
    #   file 1 = lịch kiểm tra
    #   file 2 = cán bộ trực
    #
    # thì lấy file thứ 2.
    # -----------------------------------------------------

    if len(word_files) == 2:

        ktmt = find_ktmt_file(word_files)

        if ktmt:

            for item in word_files:

                if item["path"] != ktmt["path"]:
                    return item

    return None


# =========================================================
# GIẢI NÉN ZIP
# =========================================================

async def save_and_extract_zip(file):

    tmp_dir = tempfile.mkdtemp()

    zip_path = os.path.join(
        tmp_dir,
        file.filename
    )

    try:

        data = await file.read()

        with open(zip_path, "wb") as f:
            f.write(data)

    except Exception as e:

        return None, None, {
            "error": "Không thể lưu file ZIP",
            "detail": str(e)
        }

    if not zipfile.is_zipfile(zip_path):

        return None, None, {
            "error": "File upload không phải ZIP"
        }

    try:

        with zipfile.ZipFile(
            zip_path,
            "r"
        ) as z:

            names = z.namelist()

            z.extractall(tmp_dir)

    except Exception as e:

        return None, None, {
            "error": "Không thể giải nén ZIP",
            "detail": str(e)
        }

    return tmp_dir, names, None


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
# DÙNG ĐỂ KIỂM TRA ZIP CÓ NHỮNG FILE GÌ
# =========================================================

@app.post("/list")
async def list_zip(
    file: UploadFile = File(...)
):

    tmp_dir, names, error = await save_and_extract_zip(
        file
    )

    if error:

        return JSONResponse(
            status_code=400,
            content=error
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
# EXTRACT LỊCH KIỂM TRA
#
# GIỮ NGUYÊN ENDPOINT CŨ:
#
# POST /extract
#
# Apps Script hiện tại đang gọi cái này.
# =========================================================

@app.post("/extract")
async def extract_ktmt(
    file: UploadFile = File(...)
):

    tmp_dir, names, error = await save_and_extract_zip(
        file
    )

    if error:

        return JSONResponse(
            status_code=400,
            content=error
        )

    word_files = find_word_files(
        tmp_dir
    )

    if not word_files:

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm thấy file Word trong ZIP",
                "all_files": names
            }
        )

    target = find_ktmt_file(
        word_files
    )

    if target is None:

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm được file lịch kiểm tra",
                "word_files": [
                    {
                        "filename": x["filename"],
                        "path": x["relative"]
                    }
                    for x in word_files
                ]
            }
        )

    return FileResponse(

        path=target["path"],

        filename=target["filename"],

        media_type="application/octet-stream",

        headers={
            "X-Selected-Type": "LICH KIEM TRA",
            "X-Selected-File": target["filename"]
        }
    )


# =========================================================
# EXTRACT CÁN BỘ TRỰC
#
# POST /extract-canbo
#
# MỚI
# =========================================================

@app.post("/extract-canbo")
async def extract_canbo(
    file: UploadFile = File(...)
):

    tmp_dir, names, error = await save_and_extract_zip(
        file
    )

    if error:

        return JSONResponse(
            status_code=400,
            content=error
        )

    word_files = find_word_files(
        tmp_dir
    )

    if not word_files:

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm thấy file Word trong ZIP",
                "all_files": names
            }
        )

    target = find_canbo_file(
        word_files
    )

    if target is None:

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm được file cán bộ trực",

                "word_files": [
                    {
                        "filename": x["filename"],
                        "path": x["relative"],
                        "canbo_score": score_canbo(x)
                    }
                    for x in word_files
                ]
            }
        )

    return FileResponse(

        path=target["path"],

        filename=target["filename"],

        media_type="application/octet-stream",

        headers={
            "X-Selected-Type": "CAN BO TRUC",
            "X-Selected-File": target["filename"]
        }
    )
