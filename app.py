from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
import tempfile
import os
import zipfile

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


@app.post("/extract")
async def extract(file: UploadFile = File(...)):

    tmpdir = tempfile.mkdtemp()

    zip_path = os.path.join(tmpdir, file.filename)

    with open(zip_path, "wb") as f:
        f.write(await file.read())

    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmpdir)

    target = None

    keywords = [
        "ktmt",
        "kiểm tra",
        "mục tiêu",
        "lịch ktmt"
    ]

    for root, dirs, files in os.walk(tmpdir):

        for f in files:

            name = f.lower()

            if (
                (name.endswith(".doc") or name.endswith(".docx"))
                and any(k in name for k in keywords)
            ):
                target = os.path.join(root, f)
                break

        if target:
            break

    if target is None:
        return {"error": "Không tìm thấy file KTMT"}

    return FileResponse(
        target,
        filename=os.path.basename(target)
    )
