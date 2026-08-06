import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "知微 · 小红书内容大脑",
  description: "让品牌运营经验持续沉淀、自动学习并用于内容审核。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
