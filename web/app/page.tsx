import type { ReactNode } from "react";
import Link from "next/link";
import { Camera, FileText, RefreshCw, SearchX, ShieldX, Type } from "lucide-react";
import { supabase } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type Article = {
  id: string;
  url: string;
  press: string | null;
  current_version: number;
  last_keyword: string | null;
  is_deleted: boolean;
};

type Change = {
  id: string;
  article_id: string;
  from_version: number | null;
  to_version: number | null;
  title_changed: boolean;
  body_changed: boolean;
  image_changed: boolean;
  deleted_changed: boolean;
  change_score: number;
  changed_at: string;
  articles: Article | null;
  title?: string | null;
};

export default async function HomePage() {
  const { data, error } = await supabase
    .from("article_changes")
    .select(
      `
        id,
        article_id,
        from_version,
        to_version,
        title_changed,
        body_changed,
        image_changed,
        deleted_changed,
        change_score,
        changed_at,
        articles (
          id,
          url,
          press,
          current_version,
          last_keyword,
          is_deleted
        )
      `
    )
    .order("changed_at", { ascending: false })
    .limit(50);

  if (error) {
    throw new Error(error.message);
  }

  const changes = await attachVersionTitles((data || []) as unknown as Change[]);

  return (
    <main className="page">
      <div className="pageHeader">
        <div>
          <p className="eyebrow">최근 변경</p>
          <h1>수정된 기사 목록</h1>
        </div>
        <div className="toolbar" aria-label="페이지 도구">
          <Link className="iconButton" href="/" title="새로고침">
            <RefreshCw size={18} />
          </Link>
        </div>
      </div>

      {changes.length === 0 ? (
        <div className="empty">
          <SearchX size={28} />
          <p>아직 감지된 변경이 없습니다.</p>
        </div>
      ) : (
        <div className="changeList">
          {changes.map((change) => (
            <Link
              className="changeItem"
              href={`/article/${change.article_id}?from=${change.from_version || ""}&to=${change.to_version || ""}`}
              key={change.id}
            >
              <div>
                <h2 className="itemTitle">{change.title || "제목을 불러오지 못한 기사"}</h2>
                <div className="metaRow">
                  <span>{change.articles?.press || "언론사 미확인"}</span>
                  <span>키워드 {change.articles?.last_keyword || "-"}</span>
                  <span>{formatDate(change.changed_at)}</span>
                  <span>
                    v{change.from_version} → v{change.to_version}
                  </span>
                </div>
              </div>
              <div className="badgeRow">
                {change.title_changed ? <Badge className="title" icon={<Type size={14} />} label="제목" /> : null}
                {change.body_changed ? <Badge className="body" icon={<FileText size={14} />} label="본문" /> : null}
                {change.image_changed ? <Badge className="image" icon={<Camera size={14} />} label="사진" /> : null}
                {change.deleted_changed ? <Badge className="deleted" icon={<ShieldX size={14} />} label="삭제" /> : null}
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}

function Badge({ className, icon, label }: { className: string; icon: ReactNode; label: string }) {
  return (
    <span className={`badge ${className}`}>
      {icon}
      {label}
    </span>
  );
}

async function attachVersionTitles(changes: Change[]) {
  return Promise.all(
    changes.map(async (change) => {
      if (!change.to_version) {
        return change;
      }

      const { data } = await supabase
        .from("article_versions")
        .select("title")
        .eq("article_id", change.article_id)
        .eq("version", change.to_version)
        .maybeSingle();

      return {
        ...change,
        title: data?.title || null
      };
    })
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul"
  }).format(new Date(value));
}
