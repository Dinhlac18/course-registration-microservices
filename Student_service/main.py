import os
from pathlib import Path
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Student Service - Quản lý Sinh viên")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def resolve_db_path() -> Path:
    env_db = os.getenv("DB_PATH")
    if env_db:
        return Path(env_db)
    if os.getenv("K_SERVICE"):
        return Path("/tmp/students.db")
    return Path(__file__).with_name("students.db")


DB_PATH = resolve_db_path()


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                major TEXT NOT NULL
            )
        """)

        initial_students = [
            ("SV01", "Nguyễn Minh Anh", "Công nghệ thông tin"),
            ("SV02", "Trần Hoàng Nam", "Kỹ thuật phần mềm"),
            ("SV03", "Lê Thảo Vy", "Hệ thống thông tin"),
            ("SV04", "Phạm Gia Huy", "Khoa học dữ liệu"),
        ]

        for student in initial_students:
            conn.execute(
                """
                INSERT OR IGNORE INTO students (id, name, major)
                VALUES (?, ?, ?)
                """,
                student,
            )

        conn.commit()
    finally:
        conn.close()


init_db()


class StudentCreate(BaseModel):
    id: str
    name: str
    major: str


class StudentUpdate(BaseModel):
    name: str
    major: str


@app.get("/", summary="Kiểm tra trạng thái dịch vụ")
def health_check():
    return {"service": "Student Service", "status": "ok"}


@app.get("/students", summary="Xem danh sách sinh viên")
def get_students():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, major FROM students").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/students/{student_id}", summary="Xem chi tiết sinh viên")
def get_student(student_id: str):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, major FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
        return dict(row)
    finally:
        conn.close()


@app.post("/students", summary="Thêm mới sinh viên")
def create_student(data: StudentCreate):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO students (id, name, major) VALUES (?, ?, ?)",
            (data.id, data.name, data.major),
        )
        conn.commit()
        return {"message": "Thêm sinh viên thành công", "student": data.model_dump()}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Mã sinh viên đã tồn tại")
    finally:
        conn.close()


@app.put("/students/{student_id}", summary="Cập nhật thông tin sinh viên")
def update_student(student_id: str, data: StudentUpdate):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE students SET name = ?, major = ? WHERE id = ?",
            (data.name, data.major, student_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail="Không tìm thấy sinh viên để cập nhật"
            )
        return {
            "message": "Cập nhật sinh viên thành công",
            "student_id": student_id,
            **data.model_dump(),
        }
    finally:
        conn.close()


@app.delete("/students/{student_id}", summary="Xóa sinh viên")
def delete_student(student_id: str):
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail="Không tìm thấy sinh viên để xóa"
            )
        return {"message": "Xóa sinh viên thành công", "student_id": student_id}
    finally:
        conn.close()