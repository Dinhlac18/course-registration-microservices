import os
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Course Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/tmp/courses.db" if os.getenv("VERCEL") else "courses.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL,
                course_name TEXT NOT NULL,
                credits INTEGER NOT NULL DEFAULT 3,
                schedule TEXT NOT NULL,
                max_slots INTEGER NOT NULL,
                enrolled_slots INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) AS cnt FROM sections").fetchone()["cnt"]
        if count == 0:
            conn.executemany(
                """
                INSERT INTO sections (course_code, course_name, credits, schedule, max_slots, enrolled_slots)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    ("SE301", "Kiến trúc Microservices", 3, "Thứ 2 ( Tiết 1 - 3 )", 30, 0),
                    ("SE302", "Kiểm thử phần mềm", 3, "Thứ 3 ( Tiết 4 - 6 )", 40, 0),
                ],
            )


init_db()


class SectionCreate(BaseModel):
    course_code: str
    course_name: str
    credits: int = Field(default=3, ge=1, le=4)
    schedule: str
    max_slots: int = Field(default=30, ge=1, le=150)


class SlotChange(BaseModel):
    delta: int


def _list_sections():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM sections ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def _get_section(section_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
        return dict(row)


def _create_section(data: SectionCreate):
    code = data.course_code.strip()
    name = data.course_name.strip()
    schedule = data.schedule.strip()
    if not code or not name or not schedule:
        raise HTTPException(status_code=400, detail="Thiếu thông tin học phần")

    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO sections (course_code, course_name, credits, schedule, max_slots, enrolled_slots)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (code, name, data.credits, schedule, data.max_slots),
        )
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def _update_slot(section_id: int, data: SlotChange):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")

        new_enrolled = row["enrolled_slots"] + data.delta
        if new_enrolled < 0:
            raise HTTPException(status_code=400, detail="Sĩ số đã đăng ký không thể nhỏ hơn 0")
        if new_enrolled > row["max_slots"]:
            raise HTTPException(status_code=400, detail="Lớp học phần đã hết chỗ")

        conn.execute(
            "UPDATE sections SET enrolled_slots = ? WHERE id = ?",
            (new_enrolled, section_id),
        )
        updated = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        return dict(updated)


def _delete_section(section_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
        conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
        return {"deleted": True, "id": section_id}


@app.get("/health")
@app.get("/api/courses/health")
def health():
    return {"service": "course-service", "status": "ok"}


@app.get("/sections")
@app.get("/api/courses")
@app.get("/api/courses/")
@app.get("/api/courses/sections")
def list_sections():
    return _list_sections()


@app.get("/sections/{section_id}")
@app.get("/api/courses/{section_id}")
@app.get("/api/courses/sections/{section_id}")
def get_section(section_id: int):
    return _get_section(section_id)


@app.post("/sections", status_code=201)
@app.post("/api/courses", status_code=201)
@app.post("/api/courses/", status_code=201)
@app.post("/api/courses/sections", status_code=201)
def create_section(data: SectionCreate):
    return _create_section(data)


@app.patch("/sections/{section_id}/slot")
@app.patch("/api/courses/{section_id}/slot")
@app.patch("/api/courses/sections/{section_id}/slot")
def update_slot(section_id: int, data: SlotChange):
    return _update_slot(section_id, data)


@app.delete("/sections/{section_id}")
@app.delete("/api/courses/{section_id}")
@app.delete("/api/courses/sections/{section_id}")
def delete_section(section_id: int):
    return _delete_section(section_id)