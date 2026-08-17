from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import zipfile
import os
import shutil
import unicodedata
import re

app = FastAPI()


# =========================================================
# CHUẨN HÓA TÊN
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
# TÌM TOÀN BỘ FILE WORD TRONG ZIP
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
# TÌM FILE LỊCH KIỂM TRA
# =========================================================

def find_ktmt_file(word_files):

    # Ưu tiên file có KTMT
    for item in word_files:

        name = normalize_text(
            item["filename"]
        )

        if "ktmt" in name:
            return item

    # Nếu không có KTMT thì thử "kiem tra"
    for item in word_files:

        name = normalize_text(
            item["filename"]
        )

        if "kiem tra" in name:
            return item

    return None


# =========================================================
# TÌM FILE CÁN BỘ TRỰC
# =========================================================

def find_canbo_file(word_files):

    # Với ZIP hiện tại của bạn:
    #
    # lịch công tác tuần từ 03.8 đến 09.8.2026.doc
    #
    # Đây chính là file cán bộ trực.
    #

    for item in word_files:

        name = normalize_text(
            item["filename"]
        )

        if "lich cong tac tuan" in name:
            return item

    # Trường hợp tên file khác nhưng có "cong tac"
    for item in word_files:

        name = normalize_text(
            item["filename"]
        )

        if "cong tac" in name:
            return item

    # Trường hợp có "can bo truc"
    for item in word_files:

        name = normalize_text(
            item["filename"]
        )

        if "can bo truc" in name:
            return item

    # Trường hợp có "lich truc"
    for item in word_files:

        name = normalize_text(
            item["filename"]
        )

        if "lich truc" in name:
            return item

    return None


# =========================================================
# TRANG CHỦ
# =========================================================

@app.get("/")
def home():

    return {
        "status": "ok",
        "service": "KTMT Import",
        "message": "Service is running"
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
# DEBUG ZIP
#
# POST /list
#
# Dùng để xem ZIP có những file gì
# =========================================================

@app.post("/list")
async def list_zip(
    file: UploadFile = File(...)
):

    tmp_dir = tempfile.mkdtemp(
        prefix="ktmt_list_"
    )

    zip_path = os.path.join(
        tmp_dir,
        "input.zip"
    )

    try:

        # ---------------------------------------------
        # Lưu ZIP
        # ---------------------------------------------

        data = await file.read()

        with open(zip_path, "wb") as f:
            f.write(data)

        # ---------------------------------------------
        # Kiểm tra ZIP
        # ---------------------------------------------

        if not zipfile.is_zipfile(zip_path):

            return JSONResponse(
                status_code=400,
                content={
                    "error": "File upload không phải ZIP"
                }
            )

        # ---------------------------------------------
        # Đọc ZIP
        # ---------------------------------------------

        with zipfile.ZipFile(
            zip_path,
            "r"
        ) as z:

            all_files = z.namelist()

            z.extractall(tmp_dir)

        # ---------------------------------------------
        # Tìm Word
        # ---------------------------------------------

        word_files = find_word_files(
            tmp_dir
        )

        return {
            "zip": file.filename,
            "total_files": len(all_files),

            "word_files": [
                {
                    "filename": x["filename"],
                    "path": x["relative"]
                }
                for x in word_files
            ],

            "all_files": all_files
        }

    except Exception as e:

        return JSONResponse(
            status_code=500,
            content={
                "error": "Lỗi khi xử lý ZIP",
                "detail": str(e)
            }
        )


# =========================================================
# EXTRACT
#
# /extract?kind=ktmt
# /extract?kind=canbo
# =========================================================

@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    kind: str = "ktmt"
):

    tmp_dir = tempfile.mkdtemp(
        prefix="ktmt_extract_"
    )

    zip_path = os.path.join(
        tmp_dir,
        "input.zip"
    )

    try:

        # =================================================
        # 1. NHẬN FILE
        # =================================================

        data = await file.read()

        if not data:

            return JSONResponse(
                status_code=400,
                content={
                    "error": "File ZIP rỗng"
                }
            )

        with open(zip_path, "wb") as f:
            f.write(data)


        # =================================================
        # 2. KIỂM TRA ZIP
        # =================================================

        if not zipfile.is_zipfile(zip_path):

            return JSONResponse(
                status_code=400,
                content={
                    "error": "File upload không phải ZIP"
                }
            )


        # =================================================
        # 3. GIẢI NÉN
        # =================================================

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


        # =================================================
        # 4. TÌM FILE WORD
        # =================================================

        word_files = find_word_files(
            tmp_dir
        )


        if not word_files:

            return JSONResponse(
                status_code=404,
                content={
                    "error": "Không tìm thấy file DOC/DOCX",
                    "all_files": names
                }
            )


        # =================================================
        # 5. CHỌN FILE
        # =================================================

        kind_normalized = normalize_text(
            kind
        )


        # ---------------------------------------------
        # LỊCH KIỂM TRA
        # ---------------------------------------------

        if kind_normalized == "ktmt":

            target = find_ktmt_file(
                word_files
            )

            selected_type = "LICH KIEM TRA"


        # ---------------------------------------------
        # CÁN BỘ TRỰC
        # ---------------------------------------------

        elif kind_normalized == "canbo":

            target = find_canbo_file(
                word_files
            )

            selected_type = "CAN BO TRUC"


        else:

            return JSONResponse(
                status_code=400,
                content={
                    "error": "kind không hợp lệ",
                    "kind": kind,
                    "allowed": [
                        "ktmt",
                        "canbo"
                    ]
                }
            )


        # =================================================
        # 6. KHÔNG TÌM THẤY
        # =================================================

        if target is None:

            return JSONResponse(
                status_code=404,
                content={
                    "error": "Không tìm thấy file yêu cầu",

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


        # =================================================
        # 7. COPY FILE RA NGOÀI
        #
        # Để FileResponse chắc chắn đọc được file
        # =================================================

        output_dir = tempfile.mkdtemp(
            prefix="ktmt_output_"
        )

        output_path = os.path.join(
            output_dir,
            target["filename"]
        )

        shutil.copy2(
            target["path"],
            output_path
        )


        # =================================================
        # 8. TRẢ FILE
        # =================================================

        return FileResponse(

            path=output_path,

            filename=target["filename"],

            media_type=(
                "application/msword"
                if target["filename"].lower().endswith(".doc")
                else
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),

            headers={
                "X-Selected-Type": selected_type,
                "X-Selected-File": target["filename"]
            }
        )


    except Exception as e:

        # =================================================
        # BẮT MỌI LỖI ĐỂ KHÔNG CÒN "Internal Server Error"
        # MÀ KHÔNG BIẾT NGUYÊN NHÂN
        # =================================================

        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": str(e),
                "kind": kind
            }
        )
