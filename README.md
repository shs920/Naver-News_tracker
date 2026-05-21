# News Tracker

네이버 뉴스 검색 결과를 기준으로 특정 키워드의 기사를 수집하고, 제목, 본문, 사진, 삭제 상태의 변경을 버전별로 저장한 뒤 Next.js 웹 뷰어에서 좌우 비교로 확인하는 시스템입니다.

## 구성

```text
.
├─ .github/workflows/crawl.yml
├─ crawler/
│  ├─ article_parser.py
│  ├─ config.py
│  ├─ db.py
│  ├─ diff_engine.py
│  ├─ image_hash.py
│  ├─ main.py
│  ├─ requirements.txt
│  └─ search.py
├─ database/init.sql
└─ web/
   ├─ app/
   │  ├─ article/[id]/page.tsx
   │  ├─ globals.css
   │  ├─ layout.tsx
   │  └─ page.tsx
   ├─ lib/
   │  ├─ diff.tsx
   │  └─ supabase.ts
   ├─ next.config.js
   ├─ package.json
   └─ tsconfig.json
```

## 필요한 서비스

- Supabase: PostgreSQL 데이터베이스
- GitHub Actions: 10분 주기 크롤러 실행
- Vercel: Next.js 웹 뷰어 배포

## 데이터베이스 초기화

1. Supabase 프로젝트를 생성합니다.
2. Supabase SQL Editor에서 [database/init.sql](database/init.sql)을 실행합니다.
3. 기본 키워드 `빙그레`, `삼양식품`, `농심`이 `keywords` 테이블에 등록됩니다.
4. 키워드를 추가하려면 Supabase에서 `keywords.keyword`에 값을 추가하고 `is_active=true`로 둡니다.

## 크롤러 환경변수

GitHub Actions Secrets 또는 로컬 `.env`에 설정합니다.

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `SUPABASE_URL` | 예 | Supabase Project URL |
| `SUPABASE_KEY` | 예 | Supabase `service_role` key. GitHub Secrets에만 저장하세요. |
| `REQUEST_TIMEOUT` | 아니오 | HTTP 요청 타임아웃 초. 기본값 `10` |
| `MAX_RESULTS_PER_KEYWORD` | 아니오 | 키워드별 네이버 뉴스 검색 결과 조회 개수. 기본값 `100` |
| `MAX_RECHECK_ARTICLES` | 아니오 | 기존 추적 기사 재확인 개수. 기본값 `80` |
| `MAX_KEYWORDS_PER_RUN` | 아니오 | 1회 실행에서 처리할 키워드 수. `0`이면 전체 처리. 기본값 `0` |

## 크롤러 로컬 실행

```bash
cd crawler
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell에서는 가상환경 활성화 명령이 다릅니다.

```powershell
cd crawler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

프로젝트 루트에 `.env` 파일을 만들거나 터미널 환경변수를 설정한 뒤 실행합니다.

```bash
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_KEY="your-service-role-key"
python crawler/main.py
```

Windows PowerShell:

```powershell
$env:SUPABASE_URL="https://your-project.supabase.co"
$env:SUPABASE_KEY="your-service-role-key"
python crawler/main.py
```

## GitHub Actions 설정

[.github/workflows/crawl.yml](.github/workflows/crawl.yml)은 다음 흐름으로 동작합니다.

1. 10분마다 실행
2. Python 3.11 설치
3. `crawler/requirements.txt` 설치
4. `python crawler/main.py` 실행

GitHub 저장소의 `Settings > Secrets and variables > Actions`에 아래 Secrets를 추가합니다.

| Secret 이름 | 값 |
| --- | --- |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_KEY` | Supabase service_role key |

수동 실행은 GitHub Actions 화면에서 `Crawl news changes` 워크플로를 선택한 뒤 `Run workflow`를 누르면 됩니다.

## 웹 뷰어 환경변수

Vercel Project Environment Variables 또는 로컬 `web/.env.local`에 설정합니다.

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | 예 | Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 예 | Supabase anon public key |

웹 뷰어는 읽기 전용으로 동작하므로 `service_role` key를 넣지 마세요.

## 웹 뷰어 로컬 실행

```bash
cd web
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`을 엽니다.

빌드 확인:

```bash
cd web
npm run build
```

## Vercel 배포

1. Vercel에서 GitHub 저장소를 import합니다.
2. Root Directory를 `web`으로 설정합니다.
3. Environment Variables에 `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`를 추가합니다.
4. Deploy를 실행합니다.

## 변경 감지 방식

- 제목: 공백, 따옴표, 쉼표 등 단순 기호를 제거한 뒤 유사도를 비교합니다.
- 본문: 공백과 단순 기호 차이를 줄인 정규화 텍스트로 변경 비율을 계산합니다.
- 이미지: 이미지 URL이 아니라 실제 이미지를 다운로드해 pHash를 계산하고 해밍 거리로 비교합니다.
- 삭제: HTTP `403`, `404`, `410`, 삭제 안내 문구, 비정상 메인/오류 페이지 리다이렉트를 감지합니다.

## 점검 결과

- `crawler/main.py`는 GitHub Actions에서 실행되도록 workflow와 requirements가 연결되어 있습니다.
- `crawler/requirements.txt`에는 `readability-lxml` 실행에 필요한 `lxml`을 명시했습니다.
- 네이버 검색 API의 제목/요약에서 1차 관련성 필터를 적용해 비관련 기사 fetch 시간을 줄이고, 기존 기사도 `MAX_RECHECK_ARTICLES` 개수만큼 재확인합니다.
- 본문 비교는 문단 정렬 기반으로 처리해 중간 문단 삽입 시 뒤 문단 전체가 수정된 것처럼 보이는 현상을 줄입니다.
- 웹 메인 페이지는 최근 변경 목록, 변경 유형, 언론사, 변경 시각, 버전 번호를 표시합니다.
- 웹 상세 페이지는 제목, 본문, 사진을 좌우 비교하고 변경 단어만 강조 표시합니다.

## 주의사항

- 네이버와 언론사 페이지 HTML 구조가 바뀌면 파서 보완이 필요할 수 있습니다.
- GitHub Actions 무료 사용량과 Supabase 무료 플랜 한도를 넘지 않도록 키워드 수와 재확인 개수를 조절하세요.
- `SUPABASE_KEY`에는 반드시 service_role key를 사용하되, 웹/Vercel에는 절대 노출하지 마세요.
