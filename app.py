from fastapi import FastAPI, UploadFile, File
import tempfile
import os
import zipfile

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

@app.get("/health")
def health():
    return "running"

@app.post("/upload")
async def upload(file: UploadFile = File(...)):

    suffix = os.path.splitext(file.filename)[1]

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

    tmp.write(await file.read())
    tmp.close()

    result = {
        "filename": file.filename,
        "isZip": zipfile.is_zipfile(tmp.name)
    }

    if result["isZip"]:
        with zipfile.ZipFile(tmp.name) as z:
            result["files"] = z.namelist()

    os.remove(tmp.name)

    return result
