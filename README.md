# Tiny Second-hand Shopping Platform

WHS4 시큐어 코딩 과제용 중고거래 플랫폼

## 환경 설정

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 실행 방법

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저에서 http://localhost:8000 접속.

최초 실행 시 관리자 계정이 자동 생성됩니다.
- 아이디: `admin`
- 비밀번호: `admin1234!`

**주의: 실습이 끝나면 반드시 관리자 비밀번호를 변경하거나 계정을 삭제하세요.**

## 구현된 기능

- 회원가입 / 로그인 (bcrypt 해시, 세션 쿠키 HttpOnly, 로그인 실패 잠금)
- 상품 등록 / 조회 / 검색 / 삭제 (본인 소유 검증)
- 신고 기능 (상품/유저, 중복 신고 방지, 임계치 도달 시 자동 차단/휴면)
- 유저간 송금 (잔액 검증)
- 실시간 채팅 (전체채팅 + 1:1채팅, WebSocket)
- 관리자 페이지 (유저 휴면 처리, 상품 차단, 신고 내역 확인)

## 적용된 보안 요소

| 항목 | 적용 내용 |
|---|---|
| 비밀번호 저장 | bcrypt 해시 (passlib) |
| 세션 쿠키 | HttpOnly, SameSite=Lax, 서명(itsdangerous)+만료시간(2시간) |
| CSRF | 더블 서브밋 쿠키 패턴 (csrf_token 쿠키 + 폼 hidden 필드 비교) |
| 인가(Authorization) | 상품 삭제 등에서 소유자(seller_id) 서버측 재검증, 관리자 라우트는 별도 의존성으로 서버단 체크 |
| 입력값 검증 | 아이디 정규식, 비밀번호 길이, 가격/금액 범위, 문자열 길이 제한 (서버측 재검증) |
| SQL 인젝션 | SQLAlchemy ORM 사용 (raw query 미사용) |
| XSS | Jinja2 autoescape + 채팅 프론트에서 textContent만 사용 (innerHTML 미사용) |
| 로그인 무차별 대입 방지 | 5회 실패 시 5분 잠금 |
| 신고 남용 방지 | (reporter_id, target_type, target_id) 유니크 제약으로 중복 신고 차단 |
| 에러 처리 | 커스텀 예외 핸들러로 스택트레이스/DB 정보 비노출, 로그는 서버에만 기록 |
| WebSocket 인증 | 연결 시점에 세션 쿠키 검증, 1:1 채팅방은 당사자만 join 가능 |

## 알려진 한계 / 추가로 점검이 필요한 부분

- 송금 동시성: SQLite는 행 잠금(SELECT FOR UPDATE)을 완전히 지원하지 않아 동시 요청 시 잔액 불일치 가능성이 있음. PostgreSQL 전환 시 반드시 보완.
- Rate limiting: 현재 로그인 실패 외에는 API 호출 빈도 제한이 없음 (채팅 도배, 신고 폭탄 등은 추가 구현 필요).
- CSRF 쿠키가 `Secure` 옵션 없이 설정됨 (로컬 HTTP 테스트용). HTTPS 배포 시 `secure=True`로 변경 필요.
- 파일 업로드(상품 사진)는 미구현 상태. 추가 시 확장자/MIME 검증, 파일명 난수화 등 별도 보안 처리 필요.
