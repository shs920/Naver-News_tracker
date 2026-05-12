"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { supabase } from "../../../lib/supabase";

interface Version {
  id: string;
  version: number;
  title: string | null;
  content_plain: string | null;
  image_urls: string[];
  image_hashes: string[];
  fetched_at: string;
  keyword: string | null;
}

interface Article {
  id: string;
  url: string;
  press: string | null;
  last_keyword: string | null;
  is_deleted: boolean;
}

// ── pHash 해밍 거리 ───────────────────────────────────────
function hammingDistance(a: string, b: string): number {
  try {
    const na = BigInt(`0x${a}`), nb = BigInt(`0x${b}`);
    return (na ^ nb).toString(2).split("").filter(c => c === "1").length;
  } catch { return 999; }
}

function imagesReallyChanged(
  oldHashes: string[], newHashes: string[],
  oldUrls: string[], newUrls: string[],
  threshold = 8
): boolean {
  if (oldHashes.length !== newHashes.length) return true;
  if (oldHashes.length === 0) return false;

  // pHash 비교
  if (oldHashes.length > 0 && newHashes.length > 0) {
    const used = new Set<number>();
    let matched = 0;
    for (const oh of oldHashes) {
      for (let i = 0; i < newHashes.length; i++) {
        if (used.has(i)) continue;
        if (hammingDistance(oh, newHashes[i]) <= threshold) {
          matched++; used.add(i); break;
        }
      }
    }
    const ratio = 1 - matched / Math.max(oldHashes.length, newHashes.length);
    return ratio >= 0.2;
  }

  // fallback: URL 비교
  return !oldUrls.every((u, i) => u === newUrls[i]);
}

// ── 단어 단위 diff ────────────────────────────────────────
type Token = { text: string; changed: boolean };

function wordDiff(oldText: string, newText: string): { oldTokens: Token[]; newTokens: Token[] } {
  const tok = (t: string) => (t || "").split(/(\s+)/);
  const oldW = tok(oldText), newW = tok(newText);
  const m = oldW.length, n = newW.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = oldW[i-1] === newW[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1]);

  type Op = { type: "same"|"del"|"add"; text: string };
  const ops: Op[] = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldW[i-1] === newW[j-1]) { ops.unshift({ type: "same", text: oldW[i-1] }); i--; j--; }
    else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) { ops.unshift({ type: "add", text: newW[j-1] }); j--; }
    else { ops.unshift({ type: "del", text: oldW[i-1] }); i--; }
  }

  const oldTokens: Token[] = ops.filter(o => o.type !== "add").map(o => ({ text: o.text, changed: o.type === "del" }));
  const newTokens: Token[] = ops.filter(o => o.type !== "del").map(o => ({ text: o.text, changed: o.type === "add" }));
  return { oldTokens, newTokens };
}

function renderTokens(tokens: Token[]) {
  const HL: React.CSSProperties = { background: "#ffd6d6", color: "#7a0000", fontWeight: 700, borderRadius: 2, padding: "0 1px" };
  return tokens.map((t, i) =>
    t.changed ? <mark key={i} style={HL}>{t.text}</mark> : <span key={i}>{t.text}</span>
  );
}

// ── 문단 LCS diff ─────────────────────────────────────────
type ParaDiff = { type: "same"|"del"|"add"|"change"; old?: string; new?: string };

function paragraphDiff(oldText: string, newText: string): ParaDiff[] {
  const split = (t: string) => (t || "").split(/\n+/).filter(p => p.trim());
  const oldP = split(oldText), newP = split(newText);
  const m = oldP.length, n = newP.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = oldP[i-1] === newP[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1]);

  const raw: ParaDiff[] = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldP[i-1] === newP[j-1]) { raw.unshift({ type: "same", old: oldP[i-1], new: oldP[i-1] }); i--; j--; }
    else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) { raw.unshift({ type: "add", new: newP[j-1] }); j--; }
    else { raw.unshift({ type: "del", old: oldP[i-1] }); i--; }
  }

  const merged: ParaDiff[] = [];
  for (let k = 0; k < raw.length; k++) {
    if (raw[k].type === "del" && raw[k+1]?.type === "add") {
      merged.push({ type: "change", old: raw[k].old, new: raw[k+1].new }); k++;
    } else merged.push(raw[k]);
  }
  return merged;
}

// ── 본문 좌우 비교 ────────────────────────────────────────
function BodyDiff({ oldText, newText, vA, vB }: {
  oldText: string; newText: string; vA: number; vB: number;
}) {
  const diff = paragraphDiff(oldText, newText);
  const N: React.CSSProperties = { fontSize: 13, lineHeight: 1.8, margin: "0 0 8px" };
  const C: React.CSSProperties = { ...N, background: "#fff0f0", borderRadius: 4, padding: "3px 7px", borderLeft: "3px solid #e53935" };
  const D: React.CSSProperties = { ...C, background: "#ffd6d6" };
  const E: React.CSSProperties = { margin: "0 0 8px", minHeight: 22 };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#c0392b", marginBottom: 10, paddingBottom: 6, borderBottom: "2px solid #f5c6c6" }}>
          수정 전 (v{vA})
        </div>
        {diff.map((d, idx) => {
          if (d.type === "same") return <p key={idx} style={N}>{d.old}</p>;
          if (d.type === "del")  return <p key={idx} style={D}><strong style={{ color: "#7a0000" }}>{d.old}</strong></p>;
          if (d.type === "add")  return <div key={idx} style={E} />;
          const { oldTokens } = wordDiff(d.old!, d.new!);
          return <p key={idx} style={C}>{renderTokens(oldTokens)}</p>;
        })}
      </div>
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#c0392b", marginBottom: 10, paddingBottom: 6, borderBottom: "2px solid #f5c6c6" }}>
          수정 후 (v{vB})
        </div>
        {diff.map((d, idx) => {
          if (d.type === "same") return <p key={idx} style={N}>{d.new}</p>;
          if (d.type === "del")  return <div key={idx} style={E} />;
          if (d.type === "add")  return <p key={idx} style={D}><strong style={{ color: "#7a0000" }}>{d.new}</strong></p>;
          const { newTokens } = wordDiff(d.old!, d.new!);
          return <p key={idx} style={C}>{renderTokens(newTokens)}</p>;
        })}
      </div>
    </div>
  );
}

// ── 제목 좌우 비교 ────────────────────────────────────────
function TitleDiff({ oldTitle, newTitle, vA, vB }: {
  oldTitle: string; newTitle: string; vA: number; vB: number;
}) {
  const { oldTokens, newTokens } = wordDiff(oldTitle, newTitle);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      <div style={{ background: "#fff5f5", border: "1px solid #f5c6c6", borderRadius: 8, padding: 14 }}>
        <div style={{ fontSize: 11, color: "#c0392b", fontWeight: 700, marginBottom: 8 }}>수정 전 (v{vA})</div>
        <div style={{ fontSize: 15, lineHeight: 1.6 }}>{renderTokens(oldTokens)}</div>
      </div>
      <div style={{ background: "#fff5f5", border: "1px solid #f5c6c6", borderRadius: 8, padding: 14 }}>
        <div style={{ fontSize: 11, color: "#c0392b", fontWeight: 700, marginBottom: 8 }}>수정 후 (v{vB})</div>
        <div style={{ fontSize: 15, lineHeight: 1.6 }}>{renderTokens(newTokens)}</div>
      </div>
    </div>
  );
}

// ── 메인 페이지 컴포넌트 ─────────────────────────────────
export default function ArticlePage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  const [article, setArticle] = useState<Article | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [vA, setVersionA] = useState<number>(0);
  const [vB, setVersionB] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      const [artRes, verRes] = await Promise.all([
        supabase.from("articles").select("*").eq("id", id).single(),
        supabase.from("article_versions").select("*").eq("article_id", id).order("version", { ascending: true }),
      ]);
      if (artRes.data) setArticle(artRes.data);
      if (verRes.data) {
        setVersions(verRes.data);
        const fromV = Number(searchParams.get("from"));
        const toV   = Number(searchParams.get("to"));
        const vers  = verRes.data;
        if (fromV && toV) {
          setVersionA(fromV);
          setVersionB(toV);
        } else if (vers.length >= 2) {
          setVersionA(vers[vers.length - 2].version);
          setVersionB(vers[vers.length - 1].version);
        } else if (vers.length === 1) {
          setVersionA(vers[0].version);
          setVersionB(vers[0].version);
        }
      }
      setLoading(false);
    })();
  }, [id, searchParams]);

  const verA = versions.find(v => v.version === vA);
  const verB = versions.find(v => v.version === vB);
  const titleChanged = verA && verB && verA.title !== verB.title;
  const bodyChanged  = verA && verB && verA.content_plain !== verB.content_plain;
  const imageChanged = verA && verB && imagesReallyChanged(
    verA.image_hashes || [], verB.image_hashes || [],
    verA.image_urls   || [], verB.image_urls   || [],
  );

  if (loading) return (
    <div style={{ textAlign: "center", marginTop: 100, color: "#999" }}>로딩 중...</div>
  );
  if (!article) return (
    <div style={{ textAlign: "center", marginTop: 100, color: "#999" }}>기사를 찾을 수 없습니다</div>
  );

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 16px" }}>
      {/* 뒤로가기 */}
      <button
        onClick={() => router.back()}
        style={{ background: "none", border: "none", cursor: "pointer", color: "#1a73e8", fontSize: 13, marginBottom: 16, padding: 0 }}>
        ← 목록으로
      </button>

      {/* 기사 헤더 */}
      <div style={{ background: "#fff", borderRadius: 10, padding: "16px 20px", marginBottom: 20, border: "1px solid #e0e0e0" }}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6, lineHeight: 1.4 }}>
          {verB?.title || verA?.title || "(제목 없음)"}
        </div>
        <div style={{ fontSize: 12, color: "#666", display: "flex", gap: 12, flexWrap: "wrap" }}>
          {article.press && <span>📰 {article.press}</span>}
          {article.last_keyword && (
            <span style={{ background: "#f0f0f0", padding: "1px 8px", borderRadius: 4 }}>
              {article.last_keyword}
            </span>
          )}
          <a href={article.url} target="_blank" rel="noreferrer" style={{ color: "#1a73e8" }}>
            원문 보기 →
          </a>
        </div>
      </div>

      {/* 버전 선택 */}
      <div style={{ background: "#f0f4ff", borderRadius: 8, padding: "10px 16px", marginBottom: 24, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>비교 버전:</span>
        <select
          value={vA}
          onChange={e => setVersionA(Number(e.target.value))}
          style={{ padding: "4px 8px", borderRadius: 5, border: "1px solid #ccc", fontSize: 12 }}>
          {versions.map(v => (
            <option key={v.id} value={v.version}>
              v{v.version} — {new Date(v.fetched_at).toLocaleString("ko-KR")}
            </option>
          ))}
        </select>
        <span style={{ fontWeight: 700 }}>↔</span>
        <select
          value={vB}
          onChange={e => setVersionB(Number(e.target.value))}
          style={{ padding: "4px 8px", borderRadius: 5, border: "1px solid #ccc", fontSize: 12 }}>
          {versions.map(v => (
            <option key={v.id} value={v.version}>
              v{v.version} — {new Date(v.fetched_at).toLocaleString("ko-KR")}
            </option>
          ))}
        </select>
      </div>

      {verA && verB && (
        <>
          {/* 제목 비교 */}
          {titleChanged && (
            <section style={{ background: "#fff", borderRadius: 10, padding: "16px 20px", marginBottom: 20, border: "1px solid #e0e0e0" }}>
              <h3 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 700 }}>📌 제목 변경</h3>
              <TitleDiff oldTitle={verA.title || ""} newTitle={verB.title || ""} vA={vA} vB={vB} />
            </section>
          )}

          {/* 본문 비교 */}
          <section style={{ background: "#fff", borderRadius: 10, padding: "16px 20px", marginBottom: 20, border: "1px solid #e0e0e0" }}>
            <h3 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 700 }}>📝 본문 비교</h3>
            {!bodyChanged ? (
              <p style={{ color: "#999", fontSize: 13 }}>본문 변경 없음</p>
            ) : (
              <div style={{ maxHeight: 700, overflowY: "auto", border: "1px solid #eee", borderRadius: 8, padding: "14px 16px" }}>
                <BodyDiff
                  oldText={verA.content_plain || ""}
                  newText={verB.content_plain || ""}
                  vA={vA} vB={vB}
                />
              </div>
            )}
          </section>

          {/* 사진 비교 */}
          <section style={{ background: "#fff", borderRadius: 10, padding: "16px 20px", marginBottom: 20, border: "1px solid #e0e0e0" }}>
            <h3 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 700 }}>🖼️ 사진 비교</h3>
            {!imageChanged ? (
              <p style={{ color: "#999", fontSize: 13 }}>사진 변경 없음</p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#c0392b", marginBottom: 10 }}>수정 전 (v{vA})</div>
                  {(verA.image_urls || []).map((img, i) => (
                    <img key={i} src={img} alt="" style={{ width: "100%", borderRadius: 6, border: "1px solid #ddd", marginBottom: 8 }} />
                  ))}
                  {(verA.image_urls || []).length === 0 && <p style={{ color: "#999", fontSize: 13 }}>사진 없음</p>}
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#c0392b", marginBottom: 10 }}>수정 후 (v{vB})</div>
                  {(verB.image_urls || []).map((img, i) => (
                    <img key={i} src={img} alt="" style={{ width: "100%", borderRadius: 6, border: "1px solid #ddd", marginBottom: 8 }} />
                  ))}
                  {(verB.image_urls || []).length === 0 && <p style={{ color: "#999", fontSize: 13 }}>사진 없음</p>}
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
