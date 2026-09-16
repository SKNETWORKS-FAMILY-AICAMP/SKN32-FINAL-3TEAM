"""app/routers/ — **화면·BFF 를 사람별 파일로 가른다** (병렬작업 계약 §5 · D-208).

⛔ **무엇이 있었나** — 라우트가 전부 `app/api.py` 한 파일에 있었다. 팀원 4명이 화면·BFF 를
   붙이기 시작하면 **네 사람이 같은 파일을 고친다.** §5 가 「같은 파일 두 사람 금지」라 적어
   두었는데 그 규칙을 지킬 **파일이 없었다.**

★ **가르는 축은 기능이다** (D-208).

    app/api.py          판정 코어 API — 팀장 단독 (`/health` · `/search` · `/judge` · …)
    app/routers/user.py 사용자 화면 + BFF — **ksr · lse**
    app/routers/admin.py 관리자 화면 + BFF — **ssm · psj**
    app/routers/auth.py  governor 로그인 — **팀장** (D-66 · D-213)
    app/templates/base.html  공유 레이아웃 — 팀장 (PR 로만)

🚨 **BFF 는 화면 전용 백엔드다** — 판정 코어를 다시 만들지 않는다 (D-119). 여기 있는 라우트는
   코어를 부르거나 픽스처를 읽어 **화면 모양으로 바꾸는** 일만 한다.
   ⛔ 판정 로직·검색 SQL 이 이 폴더에 들어오면 두 벌이 된다 (D-99).

🔴 **한 파일이 커지면 사람별로 쪼갠다** — `user.py` 를 두 사람이 동시에 고치게 되면
   `user_ksr.py`·`user_lse.py` 로 가르고 `api.py` 가 둘 다 `include_router` 한다.
"""

from __future__ import annotations

from app.routers.admin import router as admin_router
from app.routers.admin_errors import router as admin_errors_router
from app.routers.auth import router as auth_router
from app.routers.user import router as user_router

# 🚨 오류 로그 화면(ssm)은 `admin.py` 와 파일을 가르고 **관리자 라우터 아래에 매단다** —
#    그래서 `/admin/errors` 가 되고, 관리자 에디션에서만 붙는다 (D-213). `api.py` 는 안 고친다.
admin_router.include_router(admin_errors_router)

__all__ = ["admin_router", "auth_router", "user_router"]
