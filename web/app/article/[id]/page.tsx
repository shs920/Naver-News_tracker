"use client";

import type { CSSProperties, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
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

type HighlightTone = "before" | "after";
type DiffToken = { text: string; changed: boolean };
type DiffRow = {
  type: "same" | "add" | "delete" | "change";
  before?: string;
  after?: string;
};

const pageStyle: CSSProperties = {
  minHeight: "100vh",
  background: "#f4f5f7",
  color: "#1e1e23",
  padding: "22px 18px 56px",
};

const shellStyle: CSSProperties = {
  width: "min(1480px, 100%)",
  margin: "0 auto",
};

const topBarStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  marginBottom: 16,
};

const backButtonStyle: CSSProperties = {
  border: "1px solid #d7dce3",
  borderRadius: 6,
  background: "#fff",
  color: "#2459c5",
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 700,
  padding: "8px 11px",
};

const versionBarStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  flexWrap: "wrap",
  gap: 10,
  border: "1px solid #dfe5ee",
  borderRadius: 8,
  background: "#eef3ff",
  padding: "12px 14px",
  marginBottom: 18,
};

const articleGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
  gap: 16,
  alignItems: "start",
};

const articlePaperStyle: CSSProperties = {
  background: "#fff",
  border: "1px solid #d9dde3",
  borderRadius: 8,
  minWidth: 0,
  overflow: "hidden",
};

const articleInnerStyle: CSSProperties = {
  padding: "24px 26px 34px",
};

const labelStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  height: 28,
  borderRadius: 999,
  background: "#f1f3f6",
  color: "#5f6673",
  fontSize: 12,
  fontWeight: 800,
  padding: "0 10px",
  marginBottom: 16,
};

const headlineStyle: CSSProperties = {
  margin: "0 0 12px",
  fontSize: 28,
  lineHeight: 1.28,
  fontWeight: 800,
  letterSpacing: 0,
};

const metaStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  flexWrap: "wrap",
  gap: 8,
  color: "#6b7280",
  fontSize: 13,
  borderBottom: "1px solid #e6e8ec",
  paddingBottom: 18,
  marginBottom: 22,
};

const bodyStyle: CSSProperties = {
  fontSize: 17,
  lineHeight: 1.88,
  letterSpacing: 0,
  wordBreak: "keep-all",
  overflowWrap: "anywhere",
};

const paragraphStyle: CSSProperties = {
  margin: "0 0 18px",
};

const imageStyle: CSSProperties = {
  display: "block",
  width: "100%",
  height: "auto",
  borderRadius: 3,
  margin: "0 0 18px",
};

const beforeHighlightStyle: CSSProperties = {
  background: "#dbeafe",
  color: "#1d4ed8",
  fontWeight: 800,
  borderRadius: 3,
  boxShadow: "0 0 0 1px rgba(37, 99, 235, 0.14)",
  padding: "0 2px",
};

const afterHighlightStyle: CSSProperties = {
  background: "#ffe0de",
  color: "#a3120a",
  fontWeight: 800,
  borderRadius: 3,
  boxShadow: "0 0 0 1px rgba(211, 47, 47, 0.12)",
  padding: "0 2px",
};

const deletedNoteStyle: CSSProperties = {
  ...paragraphStyle,
  borderLeft: "3px solid #93c5fd",
  background: "#f4f8ff",
  borderRadius: 5,
  color: "#475569",
  padding: "8px 10px",
};

const selectStyle: CSSProperties = {
  height: 32,
  border: "1px solid #cbd3df",
  borderRadius: 6,
  background: "#fff",
  color: "#20242a",
  fontSize: 13,
  padding: "0 8px",
};

function hammingDistance(a: string, b: string): number {
  try {
    return (BigInt(`0x${a}`) ^ BigInt(`0x${b}`)).toString(2).split("").filter((c) => c === "1").length;
  } catch {
    return 999;
  }
}

function changedImageIndexes(beforeHashes: string[], afterHashes: string[], threshold = 8): Set<number> {
  const usedBefore = new Set<number>();
  const changed = new Set<number>();

  afterHashes.forEach((afterHash, afterIndex) => {
    const matchedBefore = beforeHashes.findIndex(
      (beforeHash, beforeIndex) => !usedBefore.has(beforeIndex) && hammingDistance(beforeHash, afterHash) <= threshold
    );
    if (matchedBefore >= 0) {
      usedBefore.add(matchedBefore);
      return;
    }
    changed.add(afterIndex);
  });

  if (beforeHashes.length !== afterHashes.length) {
    afterHashes.forEach((_, index) => {
      if (!changed.has(index) && index >= beforeHashes.length) changed.add(index);
    });
  }

  return changed;
}

function normalizeText(text: string): string {
  return (text || "")
    .toLowerCase()
    .replace(/[\s"'""''.,!?;:()[\]{}<>·ㆍ\-_/\\|~`+=*&^%$#@]+/g, "")
    .trim();
}

function similarity(a: string, b: string): number {
  const aa = normalizeText(a);
  const bb = normalizeText(b);
  if (!aa && !bb) return 1;
  if (!aa || !bb) return 0;

  const dp = Array.from({ length: aa.length + 1 }, () => new Array(bb.length + 1).fill(0));
  for (let i = 1; i <= aa.length; i++) {
    for (let j = 1; j <= bb.length; j++) {
      dp[i][j] = aa[i - 1] === bb[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp[aa.length][bb.length] / Math.max(aa.length, bb.length);
}

function splitParagraphs(text: string | null): string[] {
  return (text || "")
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function paragraphDiff(beforeText: string | null, afterText: string | null): DiffRow[] {
  const before = splitParagraphs(beforeText);
  const after = splitParagraphs(afterText);
  const beforeNorm = before.map(normalizeText);
  const afterNorm = after.map(normalizeText);
  const dp = Array.from({ length: before.length + 1 }, () => new Array(after.length + 1).fill(0));

  for (let i = 1; i <= before.length; i++) {
    for (let j = 1; j <= after.length; j++) {
      dp[i][j] = beforeNorm[i - 1] === afterNorm[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const raw: DiffRow[] = [];
  let i = before.length;
  let j = after.length;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && beforeNorm[i - 1] === afterNorm[j - 1]) {
      raw.unshift({ type: "same", before: before[i - 1], after: after[j - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      raw.unshift({ type: "add", after: after[j - 1] });
      j--;
    } else {
      raw.unshift({ type: "delete", before: before[i - 1] });
      i--;
    }
  }

  const merged: DiffRow[] = [];
  for (let index = 0; index < raw.length; index++) {
    const current = raw[index];
    const next = raw[index + 1];
    if (current.type === "delete" && next?.type === "add" && similarity(current.before || "", next.after || "") >= 0.35) {
      merged.push({ type: "change", before: current.before, after: next.after });
      index++;
    } else {
      merged.push(current);
    }
  }
  return merged;
}

function splitTokens(text: string): string[] {
  return text.match(/\s+|[^\s]+/g) || [];
}

function tokenKey(token: string): string {
  const normalized = normalizeText(token);
  return normalized || token;
}

function pairedTokenDiff(beforeText: string, afterText: string): { beforeTokens: DiffToken[]; afterTokens: DiffToken[] } {
  const before = splitTokens(beforeText);
  const after = splitTokens(afterText);
  const dp = Array.from({ length: before.length + 1 }, () => new Array(after.length + 1).fill(0));

  for (let i = 1; i <= before.length; i++) {
    for (let j = 1; j <= after.length; j++) {
      dp[i][j] = tokenKey(before[i - 1]) === tokenKey(after[j - 1]) ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const beforeTokens: DiffToken[] = [];
  const afterTokens: DiffToken[] = [];
  let i = before.length;
  let j = after.length;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && tokenKey(before[i - 1]) === tokenKey(after[j - 1])) {
      beforeTokens.unshift({ text: before[i - 1], changed: false });
      afterTokens.unshift({ text: after[j - 1], changed: false });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      afterTokens.unshift({ text: after[j - 1], changed: after[j - 1].trim().length > 0 });
      j--;
    } else {
      beforeTokens.unshift({ text: before[i - 1], changed: before[i - 1].trim().length > 0 });
      i--;
    }
  }

  return { beforeTokens, afterTokens };
}

function renderHighlightedTokens(tokens: DiffToken[], tone: HighlightTone): ReactNode {
  const style = tone === "before" ? beforeHighlightStyle : afterHighlightStyle;
  return tokens.map((token, index) =>
    token.changed ? (
      <mark key={index} style={style}>
        {token.text}
      </mark>
    ) : (
      <span key={index}>{token.text}</span>
    )
  );
}

function formatDate(value: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function VersionSelect({
  label,
  value,
  versions,
  onChange,
}: {
  label: string;
  value: number;
  versions: Version[];
  onChange: (value: number) => void;
}) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: 800 }}>
      {label}
      <select value={value} onChange={(event) => onChange(Number(event.target.value))} style={selectStyle}>
        {versions.map((version) => (
          <option key={version.id} value={version.version}>
            v{version.version} - {formatDate(version.fetched_at)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ArticlePaper({
  article,
  version,
  counterpart,
  side,
  diffRows,
  changedImages,
}: {
  article: Article;
  version: Version;
  counterpart: Version;
  side: "before" | "after";
  diffRows: DiffRow[];
  changedImages: Set<number>;
}) {
  const isAfter = side === "after";
  const titleChanged = normalizeText(version.title || "") !== normalizeText(counterpart.title || "");
  const titleTokens = titleChanged ? pairedTokenDiff(isAfter ? counterpart.title || "" : version.title || "", isAfter ? version.title || "" : counterpart.title || "") : null;

  return (
    <article style={articlePaperStyle}>
      <div style={articleInnerStyle}>
        <span style={labelStyle}>{isAfter ? `수정 후 v${version.version}` : `수정 전 v${version.version}`}</span>

        <h1 style={headlineStyle}>
          {titleTokens
            ? renderHighlightedTokens(isAfter ? titleTokens.afterTokens : titleTokens.beforeTokens, isAfter ? "after" : "before")
            : version.title || "제목 없음"}
        </h1>

        <div style={metaStyle}>
          <strong style={{ color: "#31343a" }}>{article.press || "언론사 미확인"}</strong>
          <span>{formatDate(version.fetched_at)}</span>
          {article.last_keyword ? <span style={{ color: "#6f7785" }}>키워드 {article.last_keyword}</span> : null}
          <a href={article.url} target="_blank" rel="noreferrer" style={{ color: "#2563eb", fontWeight: 800 }}>
            원문 보기
          </a>
        </div>

        <div style={bodyStyle}>
          <ImageStrip urls={version.image_urls || []} changedImages={isAfter ? changedImages : new Set()} />
          {diffRows.map((row, index) => {
            if (!isAfter) {
              if (row.type === "add") return null;
              if (row.type === "change") {
                const tokens = pairedTokenDiff(row.before || "", row.after || "").beforeTokens;
                return (
                  <p key={index} style={paragraphStyle}>
                    {renderHighlightedTokens(tokens, "before")}
                  </p>
                );
              }
              if (row.type === "delete") {
                return (
                  <p key={index} style={paragraphStyle}>
                    {renderHighlightedTokens([{ text: row.before || "", changed: true }], "before")}
                    <span style={{ marginLeft: 8, color: "#64748b", fontSize: 13, fontWeight: 700 }}>삭제됨</span>
                  </p>
                );
              }
              return (
                <p key={index} style={paragraphStyle}>
                  {row.before}
                </p>
              );
            }

            if (row.type === "same") {
              return (
                <p key={index} style={paragraphStyle}>
                  {row.after}
                </p>
              );
            }
            if (row.type === "change") {
              const tokens = pairedTokenDiff(row.before || "", row.after || "").afterTokens;
              return (
                <p key={index} style={paragraphStyle}>
                  {renderHighlightedTokens(tokens, "after")}
                </p>
              );
            }
            if (row.type === "add") {
              return (
                <p key={index} style={paragraphStyle}>
                  {renderHighlightedTokens([{ text: row.after || "", changed: true }], "after")}
                </p>
              );
            }
            return (
              <p key={index} style={deletedNoteStyle}>
                <strong style={{ color: "#1d4ed8", marginRight: 6 }}>삭제된 문단</strong>
                {row.before}
              </p>
            );
          })}
        </div>
      </div>
    </article>
  );
}

function ImageStrip({ urls, changedImages }: { urls: string[]; changedImages: Set<number> }) {
  if (!urls.length) return null;
  return (
    <div>
      {urls.map((url, index) => {
        const changed = changedImages.has(index);
        return (
          <figure key={`${url}-${index}`} style={{ margin: "0 0 20px" }}>
            <img
              src={url}
              alt=""
              style={{
                ...imageStyle,
                border: changed ? "4px solid #d93025" : "1px solid #e0e3e8",
                boxShadow: changed ? "0 0 0 4px rgba(217, 48, 37, 0.12)" : "none",
              }}
            />
            {changed ? (
              <figcaption style={{ marginTop: -8, color: "#b42318", fontSize: 13, fontWeight: 800 }}>
                변경된 사진
              </figcaption>
            ) : null}
          </figure>
        );
      })}
    </div>
  );
}

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

    async function loadArticle() {
      setLoading(true);
      const [articleResult, versionResult] = await Promise.all([
        supabase.from("articles").select("*").eq("id", id).single(),
        supabase.from("article_versions").select("*").eq("article_id", id).order("version", { ascending: true }),
      ]);

      if (articleResult.data) setArticle(articleResult.data);
      if (versionResult.data) {
        const loadedVersions = versionResult.data as Version[];
        setVersions(loadedVersions);

        const fromVersion = Number(searchParams.get("from"));
        const toVersion = Number(searchParams.get("to"));
        if (fromVersion && toVersion) {
          setVersionA(fromVersion);
          setVersionB(toVersion);
        } else if (loadedVersions.length >= 2) {
          setVersionA(loadedVersions[loadedVersions.length - 2].version);
          setVersionB(loadedVersions[loadedVersions.length - 1].version);
        } else if (loadedVersions.length === 1) {
          setVersionA(loadedVersions[0].version);
          setVersionB(loadedVersions[0].version);
        }
      }
      setLoading(false);
    }

    loadArticle();
  }, [id, searchParams]);

  const beforeVersion = versions.find((version) => version.version === vA);
  const afterVersion = versions.find((version) => version.version === vB);
  const diffRows = useMemo(
    () => paragraphDiff(beforeVersion?.content_plain || "", afterVersion?.content_plain || ""),
    [beforeVersion?.content_plain, afterVersion?.content_plain]
  );
  const changedImages = useMemo(
    () => changedImageIndexes(beforeVersion?.image_hashes || [], afterVersion?.image_hashes || []),
    [beforeVersion?.image_hashes, afterVersion?.image_hashes]
  );

  if (loading) {
    return <div style={{ ...pageStyle, textAlign: "center", paddingTop: 100, color: "#7b8491" }}>로딩 중...</div>;
  }

  if (!article || !beforeVersion || !afterVersion) {
    return <div style={{ ...pageStyle, textAlign: "center", paddingTop: 100, color: "#7b8491" }}>기사를 찾을 수 없습니다.</div>;
  }

  return (
    <main style={pageStyle}>
      <div style={shellStyle}>
        <div style={topBarStyle}>
          <button onClick={() => router.back()} style={backButtonStyle}>
            목록으로
          </button>
          <span style={{ color: "#69717d", fontSize: 13 }}>네이버 뉴스 형식 미리보기</span>
        </div>

        <div style={versionBarStyle}>
          <VersionSelect label="수정 전" value={vA} versions={versions} onChange={setVersionA} />
          <span style={{ color: "#69717d", fontWeight: 900 }}>→</span>
          <VersionSelect label="수정 후" value={vB} versions={versions} onChange={setVersionB} />
        </div>

        <div className="articleCompareGrid" style={articleGridStyle}>
          <ArticlePaper
            article={article}
            version={beforeVersion}
            counterpart={afterVersion}
            side="before"
            diffRows={diffRows}
            changedImages={changedImages}
          />
          <ArticlePaper
            article={article}
            version={afterVersion}
            counterpart={beforeVersion}
            side="after"
            diffRows={diffRows}
            changedImages={changedImages}
          />
        </div>
      </div>

      <style jsx global>{`
        @media (max-width: 980px) {
          .articleCompareGrid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </main>
  );
}
