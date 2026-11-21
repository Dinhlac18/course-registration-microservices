import os
from pathlib import Path
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel

app = FastAPI(title="Registration Service - Đăng ký Học phần")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STUDENT_SERVICE_URL = os.getenv(
    "STUDENT_SERVICE_URL", "http://127.0.0.1:8001"
).rstrip("/")
COURSE_SERVICE_URL = os.getenv(
    "COURSE_SERVICE_URL", "http://127.0.0.1:8002"
).rstrip("/")


def resolve_db_path() -> Path:
    env_db = os.getenv("DB_PATH")
    if env_db:
        return Path(env_db)
    if os.getenv("K_SERVICE"):
        return Path("/tmp/registrations.db")
    return Path(__file__).with_name("registrations.db")


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
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                UNIQUE(student_id, course_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


init_db()


class RegistrationCreate(BaseModel):
    student_id: str
    course_id: str


@app.get("/", summary="Kiểm tra trạng thái dịch vụ")
def health_check():
    return {
        "service": "Registration Service",
        "status": "ok",
        "student_service_url": STUDENT_SERVICE_URL,
        "course_service_url": COURSE_SERVICE_URL,
    }


@app.get("/registrations", summary="Xem danh sách đăng ký học phần")
def get_registrations():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, student_id, course_id FROM registrations"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.post("/registrations", summary="Đăng ký học phần cho sinh viên")
async def create_registration(data: RegistrationCreate):
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Kiểm tra sinh viên
        student_resp = await client.get(
            f"{STUDENT_SERVICE_URL}/students/{data.student_id}"
        )
        if student_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Không tìm thấy sinh viên")
        if student_resp.status_code >= 400:
            raise HTTPException(
                status_code=502, detail="Lỗi kết nối tới Student Service"
            )

        # 2. Kiểm tra học phần và số chỗ trống
        course_resp = await client.get(
            f"{COURSE_SERVICE_URL}/courses/{data.course_id}"
        )
        if course_resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Không tìm thấy học phần")
        if course_resp.status_code >= 400:
            raise HTTPException(
                status_code=502, detail="Lỗi kết nối tới Course Service"
            )

        course = course_resp.json()
        current_slots = int(course.get("slots", 0))
        if current_slots <= 0:
            raise HTTPException(status_code=400, detail="Học phần đã hết chỗ")

        # 3. Lưu đăng ký vào DB
        conn = get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO registrations (student_id, course_id) VALUES (?, ?)",
                (data.student_id, data.course_id),
            )
            conn.commit()
            reg_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=400, detail="Sinh viên đã đăng ký học phần này"
            )
        finally:
            conn.close()

        # 4. Giảm slots của học phần đi 1
        update_resp = await client.put(
            f"{COURSE_SERVICE_URL}/courses/{data.course_id}",
            json={"name": course["name"], "slots": current_slots - 1},
        )
        if update_resp.status_code >= 400:
            conn = get_connection()
            try:
                conn.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
                conn.commit()
            finally:
                conn.close()
            raise HTTPException(
                status_code=502, detail="Không thể cập nhật số lượng chỗ học phần"
            )

        return {
            "message": "Đăng ký học phần thành công",
            "registration": {
                "id": reg_id,
                "student_id": data.student_id,
                "course_id": data.course_id,
            },
        }


@app.delete("/registrations/{reg_id}", summary="Hủy đăng ký học phần")
async def cancel_registration(reg_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, student_id, course_id FROM registrations WHERE id = ?",
            (reg_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail="Không tìm thấy lượt đăng ký"
            )
        reg = dict(row)
        conn.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
        conn.commit()
    finally:
        conn.close()

    async with httpx.AsyncClient(timeout=10.0) as client:
        course_resp = await client.get(
            f"{COURSE_SERVICE_URL}/courses/{reg['course_id']}"
        )
        if course_resp.status_code == 200:
            course = course_resp.json()
            await client.put(
                f"{COURSE_SERVICE_URL}/courses/{reg['course_id']}",
                json={
                    "name": course["name"],
                    "slots": int(course.get("slots", 0)) + 1,
                },
            )

    return {"message": "Hủy đăng ký thành công", "registration_id": reg_id}