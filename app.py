from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import zipfile
import os

app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "ok",
        "service": "KTMT Import"
    }


@app.get("/health")
def health():
    return "running"


@app.post("/extract")
async def extract(file: UploadFile = File(...)):

    # Tạo thư mục tạm
    tmp_dir = tempfile.mkdtemp()

    # Lưu file ZIP
    zip_path = os.path.join(tmp_dir, file.filename)

    with open(zip_path, "wb") as f:
        f.write(await file.read())

    # Kiểm tra ZIP
    if not zipfile.is_zipfile(zip_path):
        return JSONResponse(
            status_code=400,
            content={"error": "File upload không phải ZIP"}
        )

    # Giải nén
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp_dir)

    # Tìm file KTMT
    target = None

    keywords = [
        "ktmt",
        "kiểm tra",
        "mục tiêu",
        "lịch ktmt"
    ]

    for root, dirs, files in os.walk(tmp_dir):

        for filename in files:

            name = filename.lower()

            if (
                (name.endswith(".doc") or name.endswith(".docx"))
                and any(k in name for k in keywords)
            ):
                target = os.path.join(root, filename)
                break

        if target:
            break

    if target is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Không tìm thấy file KTMT"}
        )

    # Trả đúng file Word
    return FileResponse(
        path=target,
        filename=os.path.basename(target),
        media_type="application/octet-stream"
    )
