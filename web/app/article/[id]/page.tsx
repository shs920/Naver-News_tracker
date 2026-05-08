import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { notFound } from "next/navigation";
import { changedImageIndexes, highlightedDiff } from "@/lib/diff";
import { supabase } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type Article = {
  id: string;
  url: string;
  normalized_url: string;
  press: string | null;
  current_version: number;
  is_deleted: boolean;
  last_keyword: string | null;
};

type Version = {
  id: string;
  article_id: string;
  version: number;
  keyword: string | null;
  title: string | null;
  content_plain: string | null;
  image_urls: string[];
  image_hashes: string[];
  fetched_at: string;
};

type Change = {
  id: string;
  from_version: number | null;
  to_version: number | null;
  title_changed: boolean;
  body_changed: boolean;
  image_changed: boolean;
  deleted_changed: boolean;
  changed_at: string;
};

export default async function ArticlePage({
  params,
  searchParams
}: {
  params: { id: string };
  searchParams: { from?: string; to?: string };
}) {
  const [{ data: article }, { data: versions }, { data: changes }] = await Promise.all([
    supabase.from("articles").select("*").eq("id", params.id).maybeSingle(),
    supabase.from("article_versions").select("*").eq("article_id", params.id).order("version", { ascending: true }),
    supabase.from("article_changes").select("*").eq("article_id", params.id).order("changed_at", { ascending: false })
  ]);

  if (!article || !versions?.length) {
    notFound();
  }

  const typedArticle = article as Article;
  const typedVersions = versions as Version[];
  const typedChanges = (changes || []) as Change[];
  const selected = selectVersions(typedVersions, typedChanges, searchParams);
  const before = selected.before;
  const after = selected.after;
  const changedImages = changedImageIndexes(before.image_hashes || [], after.image_hashes || []);

  return (
    <main className="page">
      <div className="compareHeader">
        <div>
          <p className="eyebrow">{typedArticle.press || "언론사 미확인"}</p>
          <h1>{after.title || before.title || "제목을 불러오지 못한 기사"}</h1>
          <div className="metaRow versionRail">
            <span>키워드 {after.keyword || typedArticle.last_keyword || "-"}</span>
            <span>
              v{before.version} → v{after.version}
            </span>
            <span>{formatDate(after.fetched_at)}</span>
            {typedArticle.is_deleted ? <span className="badge deleted">삭제 감지</span> : null}
          </div>
        </div>
        <div className="toolbar">
          <Link className="iconButton" href="/" title="목록으로">
            <ArrowLeft size={18} />
          </Link>
          <a className="externalLink" href={typedArticle.url} target="_blank" rel="noreferrer">
            원문
            <ExternalLink size={16} />
          </a>
        </div>
      </div>

      {typedChanges.length > 0 ? (
        <div className="versionRail">
          {typedChanges.map((change) => (
            <Link
              className="versionLink"
              href={`/article/${typedArticle.id}?from=${change.from_version || ""}&to=${change.to_version || ""}`}
              key={change.id}
            >
              v{change.from_version} → v{change.to_version}
            </Link>
          ))}
        </div>
      ) : null}

      <section className="section">
        <h2 className="sectionTitle">제목 비교</h2>
        <div className="compareGrid">
          <ComparePane label={`이전 v${before.version}`}>
            <p className="titleText">{highlightedDiff(before.title, after.title, "before")}</p>
          </ComparePane>
          <ComparePane label={`이후 v${after.version}`}>
            <p className="titleText">{highlightedDiff(before.title, after.title, "after")}</p>
          </ComparePane>
        </div>
      </section>

      <section className="section">
        <h2 className="sectionTitle">본문 비교</h2>
        <div className="compareGrid">
          <ComparePane label={`이전 v${before.version}`}>
            <p className="bodyText">{highlightedDiff(before.content_plain, after.content_plain, "before")}</p>
          </ComparePane>
          <ComparePane label={`이후 v${after.version}`}>
            <p className="bodyText">{highlightedDiff(before.content_plain, after.content_plain, "after")}</p>
          </ComparePane>
        </div>
      </section>

      <section className="section">
        <h2 className="sectionTitle">사진 비교</h2>
        {changedImages.before.length === 0 && changedImages.after.length === 0 ? (
          <div className="empty">변경된 사진이 없습니다.</div>
        ) : (
          <div className="compareGrid">
            <ComparePane label={`이전 v${before.version}`}>
              <ImageList version={before} indexes={changedImages.before} />
            </ComparePane>
            <ComparePane label={`이후 v${after.version}`}>
              <ImageList version={after} indexes={changedImages.after} />
            </ComparePane>
          </div>
        )}
      </section>
    </main>
  );
}

function ComparePane({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="pane">
      <p className="paneLabel">{label}</p>
      {children}
    </div>
  );
}

function ImageList({ version, indexes }: { version: Version; indexes: number[] }) {
  const urls = indexes.map((index) => version.image_urls?.[index]).filter(Boolean) as string[];
  if (urls.length === 0) {
    return <p className="muted">표시할 변경 사진이 없습니다.</p>;
  }

  return (
    <div className="imageGrid">
      {urls.map((url) => (
        <Image className="articleImage" src={url} alt="" width={640} height={400} key={url} unoptimized />
      ))}
    </div>
  );
}

function selectVersions(versions: Version[], changes: Change[], searchParams: { from?: string; to?: string }) {
  const fromVersion = Number(searchParams.from);
  const toVersion = Number(searchParams.to);
  const fromSearch = versions.find((version) => version.version === fromVersion);
  const toSearch = versions.find((version) => version.version === toVersion);

  if (fromSearch && toSearch) {
    return { before: fromSearch, after: toSearch };
  }

  const latestChange = changes[0];
  const beforeChange = versions.find((version) => version.version === latestChange?.from_version);
  const afterChange = versions.find((version) => version.version === latestChange?.to_version);

  if (beforeChange && afterChange) {
    return { before: beforeChange, after: afterChange };
  }

  const after = versions[versions.length - 1];
  const before = versions[Math.max(0, versions.length - 2)];
  return { before, after };
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul"
  }).format(new Date(value));
}
