import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Course Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "courses.db"


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
                credits INTEGER NOT NULL,
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
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                [
                    ("SE301", "Kiến trúc Microservices", 3, "Thứ 2 (Tiết 1-3)", 2),
                    ("SE302", "Kiểm thử phần mềm", 3, "Thứ 2 (Tiết 1-3)", 3),
                    ("SE305", "Điện toán đám mây", 3, "Thứ 4 (Tiết 4-6)", 2),
                ],
            )


init_db()


class SectionCreate(BaseModel):
    course_code: str
    course_name: str
    credits: int
    schedule: str
    max_slots: int


@app.get("/health")
def health():
    return {"service": "course-service", "status": "ok"}


@app.get("/sections")
def list_sections():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM sections ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


@app.get("/sections/{section_id}")
def get_section(section_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
        return dict(row)


@app.post("/sections", status_code=201)
def create_section(data: SectionCreate):
    code = data.course_code.strip()
    name = data.course_name.strip()
    schedule = data.schedule.strip()
    if not code or not name or not schedule:
        raise HTTPException(status_code=400, detail="Thiếu thông tin học phần")
    if data.credits <= 0 or data.max_slots <= 0:
        raise HTTPException(status_code=400, detail="Số tín chỉ và sĩ số tối đa phải lớn hơn 0")

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


@app.post("/sections/{section_id}/reserve")
def reserve_slot(section_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
        if row["enrolled_slots"] >= row["max_slots"]:
            raise HTTPException(status_code=409, detail="Lớp học phần đã hết chỗ")
        conn.execute(
            "UPDATE sections SET enrolled_slots = enrolled_slots + 1 WHERE id = ?",
            (section_id,),
        )
        updated = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        return dict(updated)


@app.post("/sections/{section_id}/release")
def release_slot(section_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
        if row["enrolled_slots"] > 0:
            conn.execute(
                "UPDATE sections SET enrolled_slots = enrolled_slots - 1 WHERE id = ?",
                (section_id,),
            )
        updated = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        return dict(updated)


@app.delete("/sections/{section_id}")
def delete_section(section_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
        if row["enrolled_slots"] > 0:
            raise HTTPException(
                status_code=400,
                detail="Không thể xóa vì đang có sinh viên đăng ký lớp học phần này",
            )
        conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
        return {"message": "Đã xóa lớp học phần"}