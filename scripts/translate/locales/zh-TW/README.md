# zh-TW 在地化設定

本設定面向台灣的技術學習者。譯文須保留技術含義、教學順序、可執行結構與介面契約，並使用自然、簡潔、專業的台灣繁體中文。這個版本不是簡體中文的字形替換；術語與句法須符合台灣用法。

## 編輯原則

- 直接面向學習者時使用「您」，主詞明確時不重複「我們」。
- 保留產品名稱、程式碼、指令、識別碼、檔案路徑、URL、API 欄位、模型 ID、預留位置與引用文獻的英文標題。
- 依 NVIDIA 台灣用語使用「AI 代理程式」、「執行階段」、「工作流程」、「沙箱」、「檔案」、「資料」、「資訊」與「客製化」。
- `Blueprint` 一律保留英文。程式碼與產品介面中的 `prompt`、`workflow`、`runtime`、`sandbox` 依原始契約保留。
- 同一概念在本文、可執行範例、介面文字與 SVG 圖中使用一致譯法。

## 審查門檻

這些檔案是待審查草稿。字形與詞彙檢查不能取代台灣在地審查。只有合格審查者在 Localization Studio 中逐段對照英文來源並檢查最終呈現後，才能接受來源與目標雜湊。

```bash
python3 scripts/validation/localization_audit.py --locale zh-TW
python3 scripts/validation/locale_resource_audit.py
python3 scripts/build/assemble_locale_overlay.py --self-test
```
