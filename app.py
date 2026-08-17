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

    # Chuyển ký tự đặc biệt thành khoảng trắng
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())


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
# TÍNH ĐIỂM FILE LỊCH KIỂM TRA
# =========================================================

def score_ktmt(filename):

    text = normalize_text(filename)

    score = 0

    keywords = {
        "ktmt": 100,
        "kiem tra": 80,
        "lich ktmt": 90,
        "muc tieu": 60,
        "lich kiem tra": 90,
        "lich": 20,
    }

    for keyword, value in keywords.items():

        if keyword in text:
            score += value

    return score


# =========================================================
# TÍNH ĐIỂM FILE CÁN BỘ TRỰC
# =========================================================

def score_canbo(filename):

    text = normalize_text(filename)

    score = 0

    keywords = {
        "can bo": 150,
        "can bo truc": 200,
        "canbotruc": 200,
        "truc": 80,
        "truc ban": 100,
        "truc ch": 100,
        "truc b1": 100,
        "truc b2": 30,
        "truc b3": 30,
        "lich truc": 150,
        "bo tri truc": 150,
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

            if is_word_file(filename):

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
# CHỌN FILE LỊCH KIỂM TRA
# =========================================================

def find_ktmt_file(word_files):

    if not word_files:
        return None

    scored = []

    for item in word_files:

        # Chấm cả tên file + đường dẫn
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

    # Nếu có file có điểm
    if scored[0]["score"] > 0:

        return scored[0]

    return None


# =========================================================
# CHỌN FILE CÁN BỘ TRỰC
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

    # Có từ khóa cán bộ / trực
    if scored[0]["score"] > 0:

        return scored[0]

    # -----------------------------------------------------
    # FALLBACK
    #
    # Nếu tên file hoàn toàn không có từ khóa,
    # ta thử lấy file Word thứ 2.
    #
    # Vì ZIP của bạn có:
    #   1. Lịch kiểm tra
    #   2. Cán bộ trực
    # -----------------------------------------------------

    if len(scored) >= 2:

        # Tìm file có điểm KTMT cao nhất
        ktmt = find_ktmt_file(word_files)

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
# LIỆT KÊ FILE TRONG ZIP
#
# Dùng để debug:
#
# POST /list
# =========================================================

@app.post("/list")
async def list_zip(file: UploadFile = File(...)):

    tmp_dir = tempfile.mkdtemp()

    zip_path = os.path.join(
        tmp_dir,
        file.filename
    )

    with open(zip_path, "wb") as f:

        f.write(
            await file.read()
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

            z.extractall(tmp_dir)

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
# kind=ktmt
# kind=canbo
#
# Mặc định = ktmt
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

    # -----------------------------------------------------
    # LƯU ZIP
    # -----------------------------------------------------

    try:

        data = await file.read()

        with open(zip_path, "wb") as f:

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

    if not zipfile.is_zipfile(zip_path):

        return JSONResponse(
            status_code=400,
            content={
                "error": "File upload không phải ZIP"
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

            z.extractall(tmp_dir)

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": "Không thể giải nén ZIP",
                "detail": str(e)
            }
        )


    # -----------------------------------------------------
    # TÌM FILE WORD
    # -----------------------------------------------------

    word_files = find_word_files(
        tmp_dir
    )


    if not word_files:

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm thấy file .doc hoặc .docx trong ZIP"
            }
        )


    # -----------------------------------------------------
    # CHỌN FILE
    # -----------------------------------------------------

    kind = normalize_text(kind)


    if kind in [
        "lich cong tac tuan",
        "cong tac tuan",
        "lich cong tac",
        "cong tac"
    ]:

        target = find_canbo_file(
            word_files
        )

        selected_type = "CAN BO TRUC"

    else:

        target = find_ktmt_file(
            word_files
        )

        selected_type = "LICH KIEM TRA"


    # -----------------------------------------------------
    # KHÔNG TÌM ĐƯỢC
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # TRẢ FILE
    # -----------------------------------------------------

    return FileResponse(
        path=target["path"],
        filename=target["filename"],
        media_type="application/octet-stream",
        headers={
            "X-Selected-Type": selected_type,
            "X-Selected-File": target["filename"]
        }
    )
