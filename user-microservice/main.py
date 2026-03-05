from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import RealDictCursor

# Frontend: served from expense_tracker/frontend (sibling of user-microservice)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

try:
    db_connection = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres",
        dbname="users_db",
        cursor_factory=RealDictCursor,
    )
    print("Database connection established")
    db_cursor = db_connection.cursor()
except psycopg2.Error as e:
    print("Database connection failed:", e)
    db_cursor = None


# ----- Page routes (serve frontend) -----

@app.get("/", include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse("welcome.html", {"request": request})


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/expenses", include_in_schema=False)
async def expenses_list_page(request: Request):
    return templates.TemplateResponse("expenses/list.html", {"request": request})


@app.get("/expenses/add", include_in_schema=False)
async def expenses_add_page(request: Request):
    return templates.TemplateResponse("expenses/add.html", {"request": request})


