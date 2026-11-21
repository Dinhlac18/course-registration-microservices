import os
import sqlite3
from typing import Optional
import httpx
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

DB_PATH = "/tmp/registrations.db" if os.getenv("VERCEL") else "registrations.db"
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


class RegistrationCreate(BaseModel):
    student_code: str
    section_id: int


def _list_registrations(student_code: Optional[str] = None):
    with get_db() as conn:
        if student_code:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE student_code = ? ORDER BY id ASC",
                (student_code.strip(),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM registrations ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def _create_registration(data: RegistrationCreate):
    student_code = data.student_code.strip()
    section_id = data.section_id
    if not student_code:
        raise HTTPException(status_code=400, detail="Thiếu mã sinh viên")

    with get_db() as conn:
        dup = conn.execute(
            "SELECT id FROM registrations WHERE student_code = ? AND section_id = ?",
            (student_code, section_id),
        ).fetchone()
        if dup:
            raise HTTPException(status_code=400, detail="Sinh viên đã đăng ký lớp học phần này")

    try:
        with httpx.Client(timeout=10.0) as client:
            st_resp = client.get(f"{STUDENT_SERVICE_URL}/students/{student_code}")
            if st_resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
            st_resp.raise_for_status()

            sec_resp = client.get(f"{COURSE_SERVICE_URL}/sections/{section_id}")
            if sec_resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")
            sec_resp.raise_for_status()
            section = sec_resp.json()

            if section["enrolled_slots"] >= section["max_slots"]:
                raise HTTPException(status_code=400, detail="Lớp học phần đã hết chỗ")

            slot_resp = client.patch(
                f"{COURSE_SERVICE_URL}/sections/{section_id}/slot",
                json={"delta": 1},
            )
            if slot_resp.status_code >= 400:
                detail = slot_resp.json().get("detail", "Không thể cập nhật sĩ số")
                raise HTTPException(status_code=slot_resp.status_code, detail=detail)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối service nội bộ: {exc}")

    with get_db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO registrations (student_code, section_id, course_code, course_name, schedule)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    student_code,
                    section_id,
                    section["course_code"],
                    section["course_name"],
                    section["schedule"],
                ),
            )
            row = conn.execute(
                "SELECT * FROM registrations WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Sinh viên đã đăng ký lớp học phần này")


def _delete_registration(reg_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM registrations WHERE id = ?", (reg_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lượt đăng ký")

        section_id = row["section_id"]
        conn.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))

    try:
        with httpx.Client(timeout=10.0) as client:
            client.patch(f"{COURSE_SERVICE_URL}/sections/{section_id}/slot", json={"delta": -1})
    except Exception:
        pass

    return {"deleted": True, "id": reg_id}


@app.get("/health")
@app.get("/api/registrations/health")
def health():
    return {"service": "registration-service", "status": "ok"}


@app.get("/registrations")
@app.get("/api/registrations")
@app.get("/api/registrations/")
def list_registrations(student_code: Optional[str] = None):
    return _list_registrations(student_code)


@app.post("/registrations", status_code=201)
@app.post("/api/registrations", status_code=201)
@app.post("/api/registrations/", status_code=201)
def create_registration(data: RegistrationCreate):
    return _create_registration(data)


@app.delete("/registrations/{reg_id}")
@app.delete("/api/registrations/{reg_id}")
def delete_registration(reg_id: int):
    return _delete_registration(reg_id)