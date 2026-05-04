import { redirect } from "next/navigation";

import { getCurrentProfile } from "@/lib/auth";
import { listEntities } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function ThemesPage() {
  const profile = await getCurrentProfile();
  if (!profile) redirect("/");
  const themes = await listEntities(profile, "theme");

  return (
    <main className="page">
      <div className="section-head">
        <div>
          <h1>主题</h1>
          <p className="muted">按你的订阅账号过滤后的主题观点。</p>
        </div>
      </div>
      <section className="table-panel">
        <table>
          <thead>
            <tr>
              <th>主题</th>
              <th>最近日期</th>
              <th>提及</th>
              <th>账号</th>
            </tr>
          </thead>
          <tbody>
            {themes.map((item) => (
              <tr key={item.key}>
                <td>
                  <strong>{item.displayName}</strong>
                </td>
                <td>{item.latestDate || "-"}</td>
                <td>{item.mentionCount}</td>
                <td>{item.authorCount}</td>
              </tr>
            ))}
            {!themes.length ? (
              <tr>
                <td colSpan={4}>
                  <div className="empty">暂无主题观点</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </main>
  );
}
