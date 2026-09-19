import { createContext, useContext, useLayoutEffect, useState } from "react";
import type { ReactNode } from "react";
import { Languages, Moon, Sun } from "lucide-react";
import zh from "./zh.json";

type Language = "en" | "zh";
type Theme = "light" | "dark";
const dictionary: Record<string, string> = zh;
function read(key: string) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Preferences still work without storage. */
  }
}
const initialLanguage: Language = read("rmhub-language") === "zh" ? "zh" : "en";
const savedTheme = read("rmhub-theme");
const initialTheme: Theme =
  savedTheme === "dark" || savedTheme === "light"
    ? savedTheme
    : window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
// Apply before React renders to avoid a flash of the opposite theme.
document.documentElement.dataset.theme = initialTheme;
document.documentElement.lang = initialLanguage === "zh" ? "zh-CN" : "en";

type Preferences = {
  language: Language;
  theme: Theme;
  locale: string;
  setLanguage: (language: Language) => void;
  setTheme: (theme: Theme) => void;
  t: (text: string, values?: Record<string, string | number>) => string;
};
const PreferencesContext = createContext<Preferences | null>(null);
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState(initialLanguage);
  const [theme, setTheme] = useState(initialTheme);
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    save("rmhub-theme", theme);
    save("rmhub-language", language);
  }, [theme, language]);
  const t: Preferences["t"] = (text, values = {}) => {
    const translated = language === "zh" ? (dictionary[text] ?? text) : text;
    return translated.replace(/\{(\w+)\}/g, (match, key: string) =>
      String(values[key] ?? match),
    );
  };
  return (
    <PreferencesContext.Provider
      value={{
        language,
        theme,
        locale: language === "zh" ? "zh-CN" : "en",
        setLanguage,
        setTheme,
        t,
      }}
    >
      {children}
    </PreferencesContext.Provider>
  );
}
export function usePreferences() {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("PreferencesProvider is required");
  return value;
}
export function PreferenceControls() {
  const { language, theme, setLanguage, setTheme, t } = usePreferences();
  const themeLabel = t(
    theme === "dark" ? "Switch to light mode" : "Switch to dark mode",
  );
  return (
    <div className="preference-controls">
      <button
        type="button"
        className="icon-button"
        aria-label={themeLabel}
        title={themeLabel}
        aria-pressed={theme === "dark"}
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      >
        {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
      </button>
      <label className="language-control">
        <Languages size={16} aria-hidden="true" />
        <select
          aria-label={t("Language")}
          value={language}
          onChange={(event) => setLanguage(event.target.value as Language)}
        >
          <option value="en" lang="en">
            English
          </option>
          <option value="zh" lang="zh-CN">
            中文
          </option>
        </select>
      </label>
    </div>
  );
}
