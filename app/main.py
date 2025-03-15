import os
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google.cloud import storage
from dotenv import load_dotenv
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

load_dotenv()

app = FastAPI()

# Mount static files for Bootstrap and JS
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", None)
BUCKET_NAME = os.getenv("BUCKET_NAME", "sandbox-449820.appspot.com")

assert GOOGLE_CLOUD_PROJECT, "GOOGLE_CLOUD_PROJECT environment variable is not set"
assert BUCKET_NAME, "BUCKET_NAME environment variable is not set"


def upload_to_gcs(file_path, file_name, folder: str) -> str:
    """Uploads a file to Google Cloud Storage."""
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(os.path.join(folder, file_name))
    blob.upload_from_filename(file_path)
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{folder}{file_name}"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload/record")
async def upload_audio(file: UploadFile = File(...)):
    """Handles audio file upload and saves to Google Cloud Storage."""
    file_location = f"app/static/{file.filename}"
    with open(file_location, "wb") as f:
        f.write(file.file.read())

    gcs_url = upload_to_gcs(file_location, file.filename, "audio/")
    os.remove(file_location)  # Cleanup local file after upload

    return {"message": "File uploaded successfully", "url": gcs_url}


@app.post("/upload/document")
async def upload_document(file: UploadFile = File(...)):
    """Handles document file upload and saves to Google Cloud Storage."""
    file_location = f"app/static/{file.filename}"
    with open(file_location, "wb") as f:
        f.write(file.file.read())

    gcs_url = upload_to_gcs(file_location, file.filename, "documents/")
    os.remove(file_location)

    return RedirectResponse(url="/", status_code=303)
