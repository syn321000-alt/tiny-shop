from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..dependencies import require_user
from .. import models, security

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

MAX_MESSAGE_LEN = 1000


class ConnectionManager:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, room_id: str, ws: WebSocket):
        await ws.accept()
        self.rooms[room_id].append(ws)

    def disconnect(self, room_id: str, ws: WebSocket):
        if ws in self.rooms[room_id]:
            self.rooms[room_id].remove(ws)

    async def broadcast(self, room_id: str, message: dict):
        for ws in list(self.rooms[room_id]):
            await ws.send_json(message)


manager = ConnectionManager()


def _room_id_for(user_a: int, user_b: int) -> str:
    lo, hi = sorted([user_a, user_b])
    return f"dm_{lo}_{hi}"


@router.get("/chat/global", response_class=HTMLResponse)
def global_chat_page(request: Request, user: models.User = Depends(require_user), db: Session = Depends(get_db)):
    history = (
        db.query(models.Message)
        .filter(models.Message.room_id == "global")
        .order_by(models.Message.created_at.asc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(
        "chat.html", {"request": request, "user": user, "room_id": "global", "history": history, "peer": None}
    )


@router.get("/chat/dm/{other_user_id}", response_class=HTMLResponse)
def dm_chat_page(
    other_user_id: int,
    request: Request,
    user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    peer = db.query(models.User).filter(models.User.id == other_user_id).first()
    if peer is None or peer.id == user.id:
        raise HTTPException(status_code=404)

    room_id = _room_id_for(user.id, other_user_id)
    history = (
        db.query(models.Message)
        .filter(models.Message.room_id == room_id)
        .order_by(models.Message.created_at.asc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(
        "chat.html", {"request": request, "user": user, "room_id": room_id, "history": history, "peer": peer}
    )


@router.websocket("/ws/chat/{room_id}")
async def chat_ws(websocket: WebSocket, room_id: str):
    # WebSocket 핸드셰이크 단계에서도 반드시 인증을 확인해야 한다.
    # (연결만 되면 누구나 메시지를 보낼 수 있게 두면 안 됨)
    token = websocket.cookies.get("session")
    user_id = security.read_session_token(token) if token else None
    if user_id is None:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user is None or user.is_suspended:
            await websocket.close(code=4403)
            return

        # 1:1 채팅방이면, 그 방의 당사자인지 확인 (다른 유저의 DM방에 join 못하도록)
        if room_id.startswith("dm_"):
            _, a, b = room_id.split("_")
            if str(user.id) not in (a, b):
                await websocket.close(code=4403)
                return

        await manager.connect(room_id, websocket)
        try:
            while True:
                data = await websocket.receive_json()
                content = str(data.get("content", "")).strip()[:MAX_MESSAGE_LEN]
                if not content:
                    continue

                msg = models.Message(sender_id=user.id, room_id=room_id, content=content)
                db.add(msg)
                db.commit()

                # content는 서버에서 저장만 하고, 브라우저 쪽 템플릿(Jinja2 autoescape)이나
                # 프론트 렌더링 시 반드시 이스케이프해서 출력해야 XSS를 막을 수 있음.
                await manager.broadcast(
                    room_id,
                    {"sender": user.username, "content": content, "created_at": msg.created_at.isoformat()},
                )
        except WebSocketDisconnect:
            manager.disconnect(room_id, websocket)
    finally:
        db.close()
