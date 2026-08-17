from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse

import tempfile
import zipfile
import os
import unicodedata


app = FastAPI()


# =========================================================
# HÀM CHUẨN HÓA TÊN FILE
# =========================================================

def normalize_text(text):
    """
    Chuẩn hóa chữ:
    - chuyển về chữ thường
    - bỏ dấu tiếng Việt
    - thay khoảng trắng thừa
    """

    text = str(text).lower().strip()

    text = unicodedata.normalize(
        "NFD",
        text
    )

    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )

    return " ".join(text.split())


# =========================================================
# TRANG CHỦ
# =========================================================

@app.get("/")
def home():

    return {
        "status": "ok",
        "service": "KTMT Import",
        "endpoints": [
            "/extract",
            "/extract-canbo"
        ]
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    return "running"


# =========================================================
# HÀM GIẢI NÉN ZIP
# =========================================================

def save_and_extract_zip(file, tmp_dir):

    filename = file.filename or "upload.zip"

    zip_path = os.path.join(
        tmp_dir,
        filename
    )

    return zip_path


# =========================================================
# 1. LẤY FILE LỊCH KIỂM TRA
# =========================================================

@app.post("/extract")
async def extract(file: UploadFile = File(...)):

    tmp_dir = tempfile.mkdtemp()

    filename = file.filename or "upload.zip"

    zip_path = os.path.join(
        tmp_dir,
        filename
    )

    # -----------------------------------------------------
    # Lưu ZIP
    # -----------------------------------------------------

    try:

        data = await file.read()

        with open(zip_path, "wb") as f:
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


    # -----------------------------------------------------
    # Kiểm tra ZIP
    # -----------------------------------------------------

    if not zipfile.is_zipfile(zip_path):

        return JSONResponse(
            status_code=400,
            content={
                "error":
                    "File upload không phải ZIP"
            }
        )


    # -----------------------------------------------------
    # Giải nén
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
                "error":
                    "Không thể giải nén ZIP",
                "detail":
                    str(e)
            }
        )


    # =====================================================
    # TÌM FILE LỊCH KIỂM TRA
    # =====================================================

    target = None


    # Các từ khóa dùng để nhận diện file KTMT
    keywords = [
        "ktmt",
        "kiem tra",
        "muc tieu",
        "lich ktmt"
    ]


    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            normalized_name =
                normalize_text(filename)


            # Chỉ nhận DOC / DOCX
            if not (
                normalized_name.endswith(".doc")
                or normalized_name.endswith(".docx")
            ):
                continue


            # ---------------------------------------------
            # Kiểm tra từ khóa
            # ---------------------------------------------

            if any(
                keyword in normalized_name
                for keyword in keywords
            ):

                target = os.path.join(
                    root,
                    filename
                )

                break


        if target:
            break


    # =====================================================
    # KHÔNG TÌM THẤY
    # =====================================================

    if target is None:

        return JSONResponse(
            status_code=404,
            content={
                "error":
                    "Không tìm thấy file Lịch KTMT",
                "files_found":
                    find_word_files(tmp_dir)
            }
        )


    # =====================================================
    # TRẢ FILE WORD
    # =====================================================

    return FileResponse(
        path=target,
        filename=os.path.basename(target),
        media_type="application/octet-stream"
    )


# =========================================================
# 2. LẤY FILE CÁN BỘ TRỰC
# =========================================================

@app.post("/extract-canbo")
async def extract_canbo(file: UploadFile = File(...)):

    tmp_dir = tempfile.mkdtemp()

    filename = file.filename or "upload.zip"

    zip_path = os.path.join(
        tmp_dir,
        filename
    )


    # -----------------------------------------------------
    # Lưu ZIP
    # -----------------------------------------------------

    try:

        data = await file.read()

        with open(zip_path, "wb") as f:
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


    # -----------------------------------------------------
    # Kiểm tra ZIP
    # -----------------------------------------------------

    if not zipfile.is_zipfile(zip_path):

        return JSONResponse(
            status_code=400,
            content={
                "error":
                    "File upload không phải ZIP"
            }
        )


    # -----------------------------------------------------
    # Giải nén
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
                "error":
                    "Không thể giải nén ZIP",
                "detail":
                    str(e)
            }
        )


    # =====================================================
    # TÌM FILE LỊCH CÔNG TÁC
    #
    # File này chính là file chứa:
    # - Trực CH
    # - Trực ban
    # - Trực B1
    # - Trực B2
    # - Trực B3
    #
    # Ta chỉ trả file này.
    # Apps Script sẽ chỉ lấy CH / Ban / B1.
    # =====================================================

    target = None


    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            normalized_name =
                normalize_text(filename)


            # Chỉ nhận DOC / DOCX
            if not (
                normalized_name.endswith(".doc")
                or normalized_name.endswith(".docx")
            ):
                continue


            # -------------------------------------------------
            # File thực tế của Mực:
            #
            # "lịch công tác tuần từ 03.8 đến 09.8.2026.doc"
            #
            # Sau normalize:
            #
            # "lich cong tac tuan tu 03.8 den 09.8.2026.doc"
            # -------------------------------------------------

            if (
                "lich cong tac" in normalized_name
            ):

                target = os.path.join(
                    root,
                    filename
                )

                break


        if target:
            break


    # =====================================================
    # KHÔNG TÌM THẤY
    # =====================================================

    if target is None:

        return JSONResponse(
            status_code=404,
            content={
                "error":
                    "Không tìm thấy file Lịch công tác (cán bộ trực)",
                "files_found":
                    find_word_files(tmp_dir)
            }
        )


    # =====================================================
    # TRẢ FILE WORD
    # =====================================================

    return FileResponse(
        path=target,
        filename=os.path.basename(target),
        media_type="application/octet-stream"
    )


# =========================================================
# HÀM LIỆT KÊ FILE WORD ĐỂ DEBUG
# =========================================================

def find_word_files(tmp_dir):

    result = []


    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            name = filename.lower()

            if (
                name.endswith(".doc")
                or name.endswith(".docx")
            ):

                relative_path = os.path.relpath(
                    os.path.join(root, filename),
                    tmp_dir
                )

                result.append(
                    relative_path
                )


    return result
