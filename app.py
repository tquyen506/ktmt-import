from fastapi import FastAPI

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
