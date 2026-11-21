import os
from pathlib import Path
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Course Service - Quản lý Học phần")

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
        return Path("/tmp/courses.db")
    return Path(__file__).with_name("courses.db")


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
            CREATE TABLE IF NOT EXISTS courses (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slots INTEGER NOT NULL CHECK(slots >= 0)
            )
        """)

        initial_courses = [
            ("HP01", "Lập trình Web", 30),
            ("HP02", "Cơ sở dữ liệu", 40),
            ("HP03", "Cấu trúc dữ liệu và giải thuật", 35),
            ("HP04", "Nhập môn Trí tuệ nhân tạo", 25),
            ("HP05", "An toàn và bảo mật mạng", 20),
            ("HP06", "Phân tích thiết kế hệ thống thông tin", 30),
            ("HP07", "Lập trình hướng đối tượng", 35),
            ("HP08", "Khai thác dữ liệu lớn (Big Data)", 25),
            ("HP09", "Kiểm Thử Phần Mềm", 21),
            ("HP10", "Các Nền Tảng Phát Triển Phần Mềm", 37),
            ("HP11", "Toán Cao Cấp", 40),
            ("HP12", "Trí Tuệ Nhân Tạo Nâng Cao", 2),
        ]

        for course in initial_courses:
            conn.execute(
                """
                INSERT OR IGNORE INTO courses (id, name, slots)
                VALUES (?, ?, ?)
                """,
                course,
            )

        conn.commit()
    finally:
        conn.close()


init_db()


class CourseCreate(BaseModel):
    id: str
    name: str
    slots: int = Field(gt=0)


class CourseUpdate(BaseModel):
    name: str
    slots: int = Field(ge=0)


@app.get("/", summary="Kiểm tra trạng thái dịch vụ")
def health_check():
    return {"service": "Course Service", "status": "ok"}


@app.get("/courses", summary="Xem danh sách tất cả học phần")
def get_courses():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, slots FROM courses").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/courses/{course_id}", summary="Xem thông tin chi tiết một học phần")
def get_course(course_id: str):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, slots FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy học phần")
        return dict(row)
    finally:
        conn.close()


@app.post("/courses", summary="Thêm mới một học phần")
def create_course(data: CourseCreate):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO courses (id, name, slots) VALUES (?, ?, ?)",
            (data.id, data.name, data.slots),
        )
        conn.commit()
        return {"message": "Thêm học phần thành công", "course": data.model_dump()}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Mã học phần đã tồn tại")
    finally:
        conn.close()


@app.put("/courses/{course_id}", summary="Cập nhật thông tin học phần")
def update_course(course_id: str, data: CourseUpdate):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE courses SET name = ?, slots = ? WHERE id = ?",
            (data.name, data.slots, course_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail="Không tìm thấy học phần để cập nhật"
            )
        return {
            "message": "Cập nhật học phần thành công",
            "course_id": course_id,
            **data.model_dump(),
        }
    finally:
        conn.close()


@app.delete("/courses/{course_id}", summary="Xóa học phần theo mã")
def delete_course(course_id: str):
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail="Không tìm thấy học phần để xóa"
            )
        return {"message": "Xóa học phần thành công", "course_id": course_id}
    finally:
        conn.close()