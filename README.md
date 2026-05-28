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
- GitHub Actions: 5분 주기 크롤러 실행
- Vercel: Next.js 웹 뷰어 배포

## 데이터베이스 초기화

1. Supabase 프로젝트를 생성합니다.
2. Supabase SQL Editor에서 [database/init.sql](database/init.sql)을 실행합니다.
3. 기본 식품기업 키워드가 `keywords` 테이블에 등록됩니다. 현재 기본값에는 `삼립`, `스타벅스`도 포함됩니다.
4. 키워드를 추가하려면 Supabase에서 `keywords.keyword`에 값을 추가하고 `is_active=true`로 둡니다.
5. 기존 프로젝트에 업데이트하는 경우에도 [database/init.sql](database/init.sql)을 다시 실행해 주세요. `crawler_runs` 감시 테이블과 인덱스가 추가됩니다.

## 크롤러 환경변수

GitHub Actions Secrets 또는 로컬 `.env`에 설정합니다.

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `SUPABASE_URL` | 예 | Supabase Project URL |
| `SUPABASE_KEY` | 예 | Supabase `service_role` key. GitHub Secrets에만 저장하세요. |
| `REQUEST_TIMEOUT` | 아니오 | HTTP 요청 타임아웃 초. 기본값 `10` |
| `MAX_RESULTS_PER_KEYWORD` | 아니오 | 키워드별 네이버 뉴스 검색 결과 조회 개수. 기본값 `100` |
| `MAX_SEARCH_PAGES` | 아니오 | 네이버 뉴스 API 페이지 조회 수. 100건을 넘겨 조회하려면 `MAX_RESULTS_PER_KEYWORD`와 함께 늘립니다. 기본값 `1` |
| `MAX_RECHECK_ARTICLES` | 아니오 | 기존 추적 기사 재확인 개수. 기본값 `80` |
| `RECHECK_CANDIDATE_POOL` | 아니오 | 재확인 후보 풀 크기. 최근 기사와 오래 미확인 기사에서 후보를 뽑습니다. 기본값 `800` |
| `CRAWLER_MODE` | 아니오 | `both`, `discover`, `recheck` 중 하나. GitHub Actions에서는 신규 기사 탐색과 기존 기사 재확인을 별도 job으로 실행합니다. 기본값 `both` |
| `DISCOVERY_EXCLUDED_KEYWORDS` | 아니오 | relevance 판단에는 쓰지만 별도 검색은 하지 않을 키워드 목록. 기본값 `대상웰라이프` |
| `MAX_KEYWORDS_PER_RUN` | 아니오 | 1개 crawler job에서 처리할 최대 키워드 수. `0`이면 배정된 그룹 전체 처리. 기본값 `0` |
| `KEYWORD_GROUP_INDEX` | 아니오 | 병렬 키워드 그룹 번호. GitHub Actions matrix에서 자동 설정 |
| `KEYWORD_GROUP_COUNT` | 아니오 | 병렬 키워드 그룹 개수. GitHub Actions 기본값 `4` |
| `PREFILTER_SEARCH_RESULTS` | 아니오 | 원문 fetch 전 네이버 API 제목/요약만으로 사전 필터링할지 여부. 기본값 `false` |
| `SEED_KEYWORDS` | 아니오 | 실행 시작 시 누락된 키워드를 자동 등록할 쉼표 구분 목록. 기본값에 `삼립`, `스타벅스` 포함 |

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

누락 후보를 점검하려면 프로젝트 루트에서 다음 스크립트를 실행합니다. `DIAG_KEYWORDS`를 생략하면 활성 키워드 전체를 검사합니다.

```bash
DIAG_KEYWORDS="빙그레,스타벅스" python scripts/diagnose_missing_articles.py
```

## GitHub Actions 설정

[.github/workflows/crawl.yml](.github/workflows/crawl.yml)은 다음 흐름으로 동작합니다.

1. 5분마다 실행
2. 신규 기사 탐색(`CRAWLER_MODE=discover`)과 기존 기사 재확인(`CRAWLER_MODE=recheck`)을 별도 병렬 job으로 실행
3. 신규 기사 탐색은 8개 그룹, 기존 기사 재확인은 4개 그룹으로 나뉘어 키워드와 기사 후보를 분산 처리
4. Python 3.11 설치
5. `crawler/requirements.txt` 설치
6. `python crawler/main.py` 실행
7. 각 job의 시작, 성공, 실패 상태를 Supabase `crawler_runs` 테이블에 기록

GitHub 저장소의 `Settings > Secrets and variables > Actions`에 아래 Secrets를 추가합니다.

| Secret 이름 | 값 |
| --- | --- |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_KEY` | Supabase service_role key |
| `NAVER_CLIENT_ID` | Naver Search API Client ID |
| `NAVER_CLIENT_SECRET` | Naver Search API Client Secret |

수동 실행은 GitHub Actions 화면에서 `Crawl news changes` 워크플로를 선택한 뒤 `Run workflow`를 누르면 됩니다.

워크플로는 `repository_dispatch` 이벤트도 지원합니다. 외부 감시 시스템에서 `crawl-news` 이벤트 또는 `workflow_dispatch` API를 호출하면 GitHub Actions 스케줄이 지연될 때도 크롤러를 다시 깨울 수 있습니다.

## 실행 상태 감시

크롤러는 실행할 때마다 `crawler_runs` 테이블에 아래 상태를 기록합니다.

- `running`: job 시작
- `success`: 정상 종료
- `failed`: 예외로 실패

웹 메인 화면 상단에는 최근 `discover`, `recheck` 성공 시각이 표시됩니다.

- 20분 이내: 정상
- 20~45분: 지연 의심
- 45분 초과: 중단 가능성 높음

GitHub Actions의 cron은 무료이고 편하지만, GitHub 사정에 따라 지연되거나 일부 실행이 누락될 수 있습니다. 따라서 실제 운영에서는 GitHub Actions 스케줄만 믿지 말고 외부 무료 cron을 보조 시계로 두는 것을 권장합니다.

## Cloudflare Workers Cron 감시 설정

[docs/cloudflare-worker-cron.js](docs/cloudflare-worker-cron.js)는 Supabase `crawler_runs`를 확인하고, 최근 성공 실행이 오래됐으면 GitHub Actions를 수동으로 깨우는 Worker 예시입니다.

1. Cloudflare Dashboard에서 `Workers & Pages`로 이동합니다.
2. 새 Worker를 만들고 [docs/cloudflare-worker-cron.js](docs/cloudflare-worker-cron.js) 내용을 붙여 넣습니다.
3. Worker `Settings > Variables`에 아래 값을 설정합니다.

| 이름 | 예시 | 설명 |
| --- | --- | --- |
| `GITHUB_OWNER` | `shs920` | GitHub 계정명 |
| `GITHUB_REPO` | `Naver-News_tracker` | 저장소명 |
| `GITHUB_WORKFLOW` | `crawl.yml` | 실행할 workflow 파일명 |
| `GITHUB_REF` | `main` | 실행할 브랜치 |
| `SUPABASE_URL` | `https://...supabase.co` | Supabase Project URL |
| `STALE_MINUTES` | `7` | 몇 분 이상 성공 기록이 없으면 재실행할지. GitHub Actions 준비 시간이 있으므로 15분보다 짧게 잡는 것을 권장 |
| `RUNNING_GRACE_MINUTES` | `20` | 최근 실행 중인 crawler/GitHub Actions가 있으면 중복 실행을 막는 유예 시간 |
| `DISPATCH_COOLDOWN_MINUTES` | `5` | 방금 GitHub workflow가 생성된 경우 추가 dispatch를 막는 시간 |

4. Worker `Settings > Variables > Secrets`에 아래 값을 Secret으로 추가합니다.

| 이름 | 설명 |
| --- | --- |
| `GITHUB_TOKEN` | Fine-grained GitHub token. 대상 저장소에 `Actions: Read and write` 권한 필요 |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service_role key |

5. Worker `Triggers > Cron Triggers`에서 `*/5 * * * *`를 추가합니다. 15분 주기는 권장하지 않습니다. GitHub Actions가 준비와 실행에 몇 분을 쓰기 때문에 Worker도 5분마다 상태를 확인해야 공백이 크게 벌어지지 않습니다.
6. Worker URL을 한 번 열어 JSON 결과가 나오는지 확인합니다.

`discoverAge` 또는 `recheckAge`가 `STALE_MINUTES`보다 크면 Worker가 GitHub Actions를 수동 실행합니다. 다만 최근 실행 중인 GitHub Actions나 `crawler_runs.status=running` 기록이 있으면 중복 실행하지 않습니다. GitHub Actions 자체 cron과 Worker cron을 같이 쓰면, 한쪽이 지연되어도 다른 쪽이 보완합니다.

권장 운영값:

- GitHub Actions: 현재처럼 `*/5 * * * *`
- Cloudflare Workers Cron: `*/5 * * * *`
- `STALE_MINUTES`: `7`
- `RUNNING_GRACE_MINUTES`: `20`
- `DISPATCH_COOLDOWN_MINUTES`: `5`

이 설정은 15분 이상 기다렸다가 복구하는 방식이 아니라, 마지막 성공 기록이 7분을 넘기면 선제적으로 상태를 확인하고 필요한 경우만 재실행합니다. GitHub Actions 실행 자체에 3~5분이 걸리는 현실을 감안하면 이쪽이 공백을 훨씬 작게 만듭니다.

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
- GitHub Actions는 5분마다 실행되며, 신규 기사 탐색 8개 job과 기존 기사 재확인 4개 job으로 작업을 나누어 처리합니다. 원문 fetch 전 제목/요약 사전 필터는 기본 비활성화되어 검색 결과 누락을 줄이고, 원문을 파싱한 뒤 본문 기준으로 관련성을 판단합니다.
- 본문 비교는 문단 정렬 기반으로 처리해 중간 문단 삽입 시 뒤 문단 전체가 수정된 것처럼 보이는 현상을 줄입니다.
- 웹 메인 페이지는 최근 변경 목록, 변경 유형, 언론사, 변경 시각, 버전 번호를 표시합니다.
- 웹 상세 페이지는 제목, 본문, 사진을 좌우 비교하고 변경 단어만 강조 표시합니다.

## 주의사항

- 네이버와 언론사 페이지 HTML 구조가 바뀌면 파서 보완이 필요할 수 있습니다.
- GitHub Actions 무료 사용량과 Supabase 무료 플랜 한도를 넘지 않도록 키워드 수와 재확인 개수를 조절하세요.
- `SUPABASE_KEY`에는 반드시 service_role key를 사용하되, 웹/Vercel에는 절대 노출하지 마세요.
