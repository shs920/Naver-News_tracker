"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { supabase } from "../lib/supabase";

interface ArticleChange {
  id: string;
  article_id: string;
  from_version: number;
  to_version: number;
  title_changed: boolean;
  body_changed: boolean;
  image_changed: boolean;
  deleted_changed: boolean;
  change_score: number;
  changed_at: string;
  articles: {
    id: string;
    url: string;
    press: string | null;
    last_keyword: string | null;
    is_deleted: boolean;
  };
  title: string | null;
}

const PAGE_SIZE = 50;

const BADGE_STYLE: Record<string, React.CSSProperties> = {
  제목: { background: "#e8f0fe", color: "#1a73e8", border: "1px solid #c5d8f9" },
  본문: { background: "#e6f4ea", color: "#137333", border: "1px solid #b7dfc2" },
  사진: { background: "#fce8b2", color: "#7a4f00", border: "1px solid #f0c060" },
  삭제: { background: "#fce8e6", color: "#c5221f", border: "1px solid #f5b8b5" },
};

function Badge({ label }: { label: string }) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, borderRadius: 4,
      padding: "2px 7px", marginRight: 4,
      ...BADGE_STYLE[label],
    }}>
      {label}
    </span>
  );
}

export default function HomePage() {
  const [changes, setChanges] = useState<ArticleChange[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  // keywords 테이블에서 동적으로 로드
  useEffect(() => {
    supabase
      .from("keywords")
      .select("keyword")
      .eq("is_active", true)
      .order("keyword")
      .then(({ data }) => {
        if (data) setKeywords(data.map((r: { keyword: string }) => r.keyword));
      });
  }, []);

  const fetchChanges = useCallback(async (p: number, kw: string) => {
    setLoading(true);
    setErrorMessage("");

    // 키워드 필터: articles 테이블에서 article_id 목록 먼저 조회
    let articleIds: string[] | null = null;
    if (kw) {
      const { data: kwArticles } = await supabase
        .from("articles")
        .select("id")
        .eq("last_keyword", kw);
      articleIds = (kwArticles || []).map((a: { id: string }) => a.id);
      if (articleIds.length === 0) {
        setChanges([]);
        setTotal(0);
        setLoading(false);
        return;
      }
    }

    // Count matching changes first so pagination stays accurate.
    let countQ = supabase
      .from("article_changes")
      .select("id", { count: "exact", head: true });
    if (articleIds) countQ = countQ.in("article_id", articleIds);
    const { count, error: countError } = await countQ;
    if (countError) {
      console.error("count error:", countError);
      setErrorMessage(countError.message);
      setChanges([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    setTotal(count || 0);

    // Fetch changes first. article_versions has no direct FK to article_changes,
    // so version titles are fetched separately and merged client-side.
    let q = supabase
      .from("article_changes")
      .select(`
        id, article_id, from_version, to_version,
        title_changed, body_changed, image_changed, deleted_changed,
        change_score, changed_at,
        articles ( id, url, press, last_keyword, is_deleted )
      `)
      .order("changed_at", { ascending: false })
      .range(p * PAGE_SIZE, (p + 1) * PAGE_SIZE - 1);
    if (articleIds) q = q.in("article_id", articleIds);

    const { data, error } = await q;
    if (error) {
      console.error("fetch error:", error);
      setErrorMessage(error.message);
      setChanges([]);
      setLoading(false);
      return;
    }

    const rawChanges = (data || []) as unknown as Omit<ArticleChange, "title">[];
    if (rawChanges.length === 0) {
      setChanges([]);
      setLoading(false);
      return;
    }

    const ids = Array.from(new Set(rawChanges.map(c => c.article_id)));
    const versions = Array.from(new Set(rawChanges.map(c => c.to_version)));
    const { data: versionRows, error: versionError } = await supabase
      .from("article_versions")
      .select("article_id, version, title")
      .in("article_id", ids)
      .in("version", versions);

    if (versionError) {
      console.error("version fetch error:", versionError);
      setErrorMessage(versionError.message);
      setChanges(rawChanges.map(c => ({ ...c, title: null })));
      setLoading(false);
      return;
    }

    const titleByChange = new Map<string, string | null>();
    for (const row of versionRows || []) {
      titleByChange.set(`${row.article_id}:${row.version}`, row.title);
    }

    setChanges(rawChanges.map(c => ({
      ...c,
      title: titleByChange.get(`${c.article_id}:${c.to_version}`) || null,
    })));
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchChanges(page, keyword);
  }, [page, keyword, fetchChanges]);

  useEffect(() => {
    const t = setInterval(() => fetchChanges(page, keyword), 60000);
    return () => clearInterval(t);
  }, [page, keyword, fetchChanges]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 16px" }}>
      {/* 헤더 */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 700 }}>
          🍜 식품 기업 뉴스 수정 추적기
        </h1>
        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          기사 제목·본문·사진의 수정 내역을 실시간으로 추적합니다
        </p>
      </div>

      {/* 키워드 필터 — Supabase keywords 테이블에서 동적 로드 */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
        {["", ...keywords].map(kw => (
          <button
            key={kw}
            onClick={() => { setKeyword(kw); setPage(0); }}
            style={{
              padding: "5px 14px", borderRadius: 20, fontSize: 13,
              border: "1px solid #ccc", cursor: "pointer",
              background: keyword === kw ? "#1a73e8" : "#fff",
              color: keyword === kw ? "#fff" : "#333",
              fontWeight: keyword === kw ? 600 : 400,
            }}>
            {kw || "전체"}
          </button>
        ))}
      </div>

      {/* 목록 */}
      {loading && <p style={{ color: "#999", textAlign: "center" }}>로딩 중...</p>}
      {!loading && errorMessage && (
        <p style={{ color: "#c5221f", textAlign: "center", marginTop: 40 }}>
          Supabase 조회 오류: {errorMessage}
        </p>
      )}
      {!loading && changes.length === 0 && (
        <p style={{ color: "#999", textAlign: "center", marginTop: 60 }}>
          수정된 기사가 없습니다
        </p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {changes.map(c => {
          const article = c.articles;
          const title = c.title || "(제목 없음)";
          const types: string[] = [];
          if (c.title_changed) types.push("제목");
          if (c.body_changed) types.push("본문");
          if (c.image_changed) types.push("사진");
          if (c.deleted_changed) types.push("삭제");

          return (
            <Link
              key={c.id}
              href={`/article/${article?.id}?from=${c.from_version}&to=${c.to_version}`}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div style={{
                background: "#fff", borderRadius: 10, padding: "14px 16px",
                border: "1px solid #e0e0e0",
                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8 }}>
                  <div style={{ flex: 1, fontSize: 14, fontWeight: 600, lineHeight: 1.4 }}>
                    {title}
                  </div>
                  <div style={{ fontSize: 11, color: "#999", flexShrink: 0, whiteSpace: "nowrap" }}>
                    v{c.from_version} → v{c.to_version}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  {types.map(t => <Badge key={t} label={t} />)}
                  <span style={{ fontSize: 11, color: "#888" }}>
                    {article?.press && <>{article.press} · </>}
                    {article?.last_keyword && (
                      <span style={{ background: "#f0f0f0", padding: "1px 6px", borderRadius: 4, marginRight: 4 }}>
                        {article.last_keyword}
                      </span>
                    )}
                    {new Date(c.changed_at).toLocaleString("ko-KR")}
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, marginTop: 24 }}>
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{ padding: "6px 16px", borderRadius: 6, border: "1px solid #ccc", cursor: page === 0 ? "not-allowed" : "pointer", background: "#fff" }}>
            ◀ 이전
          </button>
          <span style={{ fontSize: 13, color: "#666" }}>{page + 1} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            style={{ padding: "6px 16px", borderRadius: 6, border: "1px solid #ccc", cursor: page >= totalPages - 1 ? "not-allowed" : "pointer", background: "#fff" }}>
            다음 ▶
          </button>
        </div>
      )}
    </div>
  );
}
