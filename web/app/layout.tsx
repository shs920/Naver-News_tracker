import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "식품 기업 뉴스 추적기",
  description: "식품 기업 관련 뉴스 기사의 제목·본문·사진 수정을 추적합니다",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f5f5f5" }}>
        {children}
      </body>
    </html>
  );
}
