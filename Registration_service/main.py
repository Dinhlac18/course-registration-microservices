import os
import sqlite3
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Registration Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "registrations.db"
STUDENT_SERVICE_URL = os.getenv("STUDENT_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")
COURSE_SERVICE_URL = os.getenv("COURSE_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT NOT NULL,
                section_id INTEGER NOT NULL,
                course_code TEXT NOT NULL,
                course_name TEXT NOT NULL,
                schedule TEXT NOT NULL,
                UNIQUE(student_code, section_id)
            )
            """
        )


init_db()


class RegisterRequest(BaseModel):
    student_code: str
    section_id: int


@app.get("/health")
def health():
    return {"service": "registration-service", "status": "ok"}


@app.get("/registrations")
def list_registrations(student_code: str | None = None):
    with get_db() as conn:
        if student_code:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE student_code = ? ORDER BY id DESC",
                (student_code.strip(),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM registrations ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@app.post("/registrations", status_code=201)
def register_course(req: RegisterRequest):
    student_code = req.student_code.strip()

    st_res = requests.get(f"{STUDENT_SERVICE_URL}/students/{student_code}", timeout=5)
    if st_res.status_code != 200:
        raise HTTPException(status_code=404, detail="Mã sinh viên không tồn tại")

    sec_res = requests.get(f"{COURSE_SERVICE_URL}/sections/{req.section_id}", timeout=5)
    if sec_res.status_code != 200:
        raise HTTPException(status_code=404, detail="Lớp học phần không tồn tại")
    section = sec_res.json()

    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM registrations WHERE student_code = ?", (student_code,)
        ).fetchall()
        for item in existing:
            if item["section_id"] == req.section_id:
                raise HTTPException(status_code=400, detail="Bạn đã đăng ký lớp học phần này rồi")
            if item["schedule"] == section["schedule"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Trùng lịch học ({section['schedule']}) với môn {item['course_name']}",
                )

    reserve_res = requests.post(
        f"{COURSE_SERVICE_URL}/sections/{req.section_id}/reserve", timeout=5
    )
    if reserve_res.status_code != 200:
        detail = reserve_res.json().get("detail", "Không thể giữ chỗ lớp học phần")
        raise HTTPException(status_code=reserve_res.status_code, detail=detail)

    try:
        with get_db() as conn:
            cur = conn.execute(
                """
                INSERT INTO registrations (student_code, section_id, course_code, course_name, schedule)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    student_code,
                    req.section_id,
                    section["course_code"],
                    section["course_name"],
                    section["schedule"],
                ),
            )
            row = conn.execute("SELECT * FROM registrations WHERE id = ?", (cur.lastrowid,)).fetchone()
            return dict(row)
    except Exception:
        requests.post(f"{COURSE_SERVICE_URL}/sections/{req.section_id}/release", timeout=5)
        raise HTTPException(status_code=500, detail="Lỗi lưu đăng ký, đã hoàn lại slot")


@app.delete("/registrations/{reg_id}")
def cancel_registration(reg_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi đăng ký")
        section_id = row["section_id"]
        conn.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))

    requests.post(f"{COURSE_SERVICE_URL}/sections/{section_id}/release", timeout=5)
    return {"message": "Đã hủy đăng ký học phần"}