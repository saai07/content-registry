# Content Registry

A FastAPI microservice for uploading and classifying educational content.

## Quick Start

```bash
# Create virtual environment
python -m venv env

# Activate (Windows)
.\env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload --port 8000
```

## API Docs

Once running, open **http://localhost:8000/docs** for interactive Swagger UI.

## Endpoints

| Method   | Endpoint                       | Description                  |
|----------|--------------------------------|------------------------------|
| `POST`   | `/api/content/upload`          | Upload file + metadata       |
| `GET`    | `/api/content`                 | List all (with filters)      |
| `GET`    | `/api/content/{id}`            | Get content details          |
| `GET`    | `/api/content/{id}/download`   | Download the file            |
| `DELETE` | `/api/content/{id}`            | Delete content + file        |
| `GET`    | `/api/metadata/classes`        | List available classes       |
| `GET`    | `/api/metadata/subjects`       | List subjects                |
| `GET`    | `/api/metadata/chapters`       | List chapters                |

## Project Structure

```
content-registry/
├── app/
│   ├── main.py         # FastAPI entry point
│   ├── database.py     # SQLite layer
│   ├── models.py       # Pydantic schemas
│   ├── config.py       # Configuration
│   └── routers/
│       ├── content.py  # Content CRUD endpoints
│       └── metadata.py # Metadata endpoints
├── uploads/            # Stored files (gitignored)
├── data/               # SQLite DB (gitignored)
└── requirements.txt
```