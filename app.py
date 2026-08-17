from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import zipfile
import os
import shutil

app = FastAPI()


# =========================================================
# TRANG CHỦ
# =========================================================

@app.get("/")
def home():
    return {
        "status": "ok",
        "service": "KTMT Import"
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

async def save_and_extract_zip(file: UploadFile):

    tmp_dir = tempfile.mkdtemp()

    zip_path = os.path.join(
        tmp_dir,
        file.filename or "upload.zip"
    )

    with open(zip_path, "wb") as f:
        f.write(await file.read())

    # Kiểm tra ZIP
    if not zipfile.is_zipfile(zip_path):

        shutil.rmtree(
            tmp_dir,
            ignore_errors=True
        )

        return None, None

    # Giải nén an toàn
    with zipfile.ZipFile(zip_path, "r") as z:

        for member in z.infolist():

            member_path = os.path.abspath(
                os.path.join(
                    tmp_dir,
                    member.filename
                )
            )

            if not member_path.startswith(
                os.path.abspath(tmp_dir) + os.sep
            ):
                shutil.rmtree(
                    tmp_dir,
                    ignore_errors=True
                )

                return None, None

        z.extractall(tmp_dir)

    return tmp_dir, zip_path


# =========================================================
# TÌM FILE LỊCH KIỂM TRA
# =========================================================

def find_ktmt_file(tmp_dir):

    keywords = [
        "ktmt",
        "kiểm tra",
        "mục tiêu",
        "lịch ktmt"
    ]

    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            name = filename.lower().strip()

            if not (
                name.endswith(".doc")
                or name.endswith(".docx")
            ):
                continue

            for keyword in keywords:

                if keyword in name:

                    return os.path.join(
                        root,
                        filename
                    )

    return None


# =========================================================
# TÌM FILE CÁN BỘ TRỰC
# =========================================================

def find_canbo_truc_file(tmp_dir):

    # Ưu tiên tên file có cụm "cán bộ trực"
    priority_keywords = [
        "cán bộ trực",
        "can bo truc",
        "cán bộtrực",
        "canbotruc",
        "cán bộ",
        "can bo"
    ]

    # Tên dự phòng
    secondary_keywords = [
        "trực",
        "truc"
    ]

    candidates = []

    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            name = filename.lower().strip()

            if not (
                name.endswith(".doc")
                or name.endswith(".docx")
            ):
                continue

            full_path = os.path.join(
                root,
                filename
            )

            # =========================================
            # ƯU TIÊN 1: "CÁN BỘ TRỰC"
            # =========================================

            for keyword in priority_keywords:

                if keyword in name:

                    return full_path

            # =========================================
            # LƯU FILE CÓ TỪ "TRỰC"
            # =========================================

            for keyword in secondary_keywords:

                if keyword in name:

                    candidates.append(
                        full_path
                    )

                    break

    # Nếu không có tên "cán bộ trực"
    # thì lấy file có chữ "trực"
    if len(candidates) > 0:

        return candidates[0]

    return None


# =========================================================
# API CŨ:
# LẤY FILE LỊCH KIỂM TRA
# =========================================================

@app.post("/extract")
async def extract(file: UploadFile = File(...)):

    tmp_dir, zip_path = await save_and_extract_zip(file)

    if tmp_dir is None:

        return JSONResponse(
            status_code=400,
            content={
                "error": "File upload không phải ZIP"
            }
        )

    # Tìm file KTMT
    target = find_ktmt_file(tmp_dir)

    if target is None:

        shutil.rmtree(
            tmp_dir,
            ignore_errors=True
        )

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm thấy file KTMT"
            }
        )

    # Trả file Word
    return FileResponse(
        path=target,
        filename=os.path.basename(target),
        media_type="application/octet-stream"
    )


# =========================================================
# API MỚI:
# LẤY FILE CÁN BỘ TRỰC
# =========================================================

@app.post("/extract-canbo")
async def extract_canbo(file: UploadFile = File(...)):

    tmp_dir, zip_path = await save_and_extract_zip(file)

    if tmp_dir is None:

        return JSONResponse(
            status_code=400,
            content={
                "error": "File upload không phải ZIP"
            }
        )

    # Tìm file cán bộ trực
    target = find_canbo_truc_file(tmp_dir)

    if target is None:

        shutil.rmtree(
            tmp_dir,
            ignore_errors=True
        )

        return JSONResponse(
            status_code=404,
            content={
                "error": "Không tìm thấy file Cán bộ trực"
            }
        )

    # Trả file Word
    return FileResponse(
        path=target,
        filename=os.path.basename(target),
        media_type="application/octet-stream"
    )
