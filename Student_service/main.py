import os
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Student Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/tmp/students.db" if os.getenv("VERCEL") else "students.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                major TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO students (student_code, full_name, major)
            VALUES ('SV001', 'Nguyễn Văn A', 'Kỹ thuật phần mềm'),
                   ('SV002', 'Trần Thị B', 'Công nghệ thông tin')
            """
        )


init_db()


class StudentCreate(BaseModel):
    student_code: str
    full_name: str
    major: str


class StudentUpdate(BaseModel):
    full_name: str
    major: str


def _list_students():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM students ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def _get_student(student_code: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE student_code = ?", (student_code,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
        return dict(row)


def _create_student(data: StudentCreate):
    code = data.student_code.strip()
    name = data.full_name.strip()
    major = data.major.strip()
    if not code or not name or not major:
        raise HTTPException(status_code=400, detail="Thiếu thông tin sinh viên")

    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO students (student_code, full_name, major) VALUES (?, ?, ?)",
                (code, name, major),
            )
            return {
                "id": cur.lastrowid,
                "student_code": code,
                "full_name": name,
                "major": major,
            }
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Mã sinh viên đã tồn tại")


def _update_student(student_code: str, data: StudentUpdate):
    code = student_code.strip()
    name = data.full_name.strip()
    major = data.major.strip()
    if not name or not major:
        raise HTTPException(status_code=400, detail="Họ tên và ngành học không được để trống")

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE student_code = ?", (code,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")

        conn.execute(
            "UPDATE students SET full_name = ?, major = ? WHERE student_code = ?",
            (name, major, code),
        )
        updated = conn.execute(
            "SELECT * FROM students WHERE student_code = ?", (code,)
        ).fetchone()
        return dict(updated)


@app.get("/health")
@app.get("/api/students/health")
def health():
    return {"service": "student-service", "status": "ok"}


@app.get("/students")
@app.get("/api/students")
@app.get("/api/students/")
def list_students():
    return _list_students()


@app.get("/students/{student_code}")
@app.get("/api/students/{student_code}")
def get_student(student_code: str):
    return _get_student(student_code)


@app.post("/students", status_code=201)
@app.post("/api/students", status_code=201)
@app.post("/api/students/", status_code=201)
def create_student(data: StudentCreate):
    return _create_student(data)


@app.put("/students/{student_code}")
@app.put("/api/students/{student_code}")
def update_student(student_code: str, data: StudentUpdate):
    return _update_student(student_code, data)