import { usePreferences } from "../preferences";
import { useState } from "react";
import type { Event } from "../types";
import { useData } from "../useData";
import { formatDate } from "../api";
import { Heading, Load, Empty, Badge, LinkOut } from "../components";

export function TimelinePage({ revision }: { revision: number }) {
  const { t, locale } = usePreferences();
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [omit, setOmit] = useState(true);
  const [group, setGroup] = useState("day");
  const state = useData<Event[]>(
    `/timeline?${new URLSearchParams({ q, source, omit_overdue: String(omit) })}`,
    revision,
  );
  return (
    <>
      <Heading
        title={t("Team timeline")}
        description={t("Tasks, conversations, and meetings in one place.")}
      />
      <div className="toolbar">
        <input
          aria-label={t("Search timeline")}
          placeholder={t("Search updates…")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          aria-label={t("Source")}
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          <option value="">{t("All sources")}</option>
          {["feishu", "bitable", "message", "meeting", "mock"].map((s) => (
            <option key={s} value={s}>
              {t(s)}
            </option>
          ))}
        </select>
        <select
          aria-label={t("Group timeline")}
          value={group}
          onChange={(e) => setGroup(e.target.value)}
        >
          <option value="day">{t("By day")}</option>
          <option value="source">{t("By source")}</option>
        </select>
        <label className="inline">
          <input
            type="checkbox"
            checked={omit}
            onChange={(e) => setOmit(e.target.checked)}
          />
          {t("Omit past items")}
        </label>
      </div>
      <Load state={state}>
        {(events) => {
          const buckets: Record<string, Event[]> = {};
          events.forEach((e) => {
            const key =
              group === "source"
                ? e.source
                : e.ts
                  ? new Date(e.ts).toLocaleDateString(locale)
                  : "Undated";
            (buckets[key] ??= []).push(e);
          });
          return events.length ? (
            <div className="timeline">
              {Object.entries(buckets).map(([key, items]) => (
                <section key={key}>
                  <h2>{t(key)}</h2>
                  {items.map((e) => (
                    <article className="panel timeline-item" key={e.id}>
                      <div className="card-meta">
                        <Badge value={e.source} />
                        <small>{formatDate(e.ts, locale)}</small>
                        <LinkOut url={e.url} />
                      </div>
                      <h3>{e.title}</h3>
                      <p>{e.description}</p>
                      <small>{e.author}</small>
                    </article>
                  ))}
                </section>
              ))}
            </div>
          ) : (
            <Empty>{t("No timeline items match your filters.")}</Empty>
          );
        }}
      </Load>
    </>
  );
}
