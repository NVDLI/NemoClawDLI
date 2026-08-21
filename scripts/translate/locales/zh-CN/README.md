# zh-CN 本地化配置

本配置面向中国大陆的技术学习者。译文需要完整保留技术含义、教学顺序、可执行结构和界面契约，同时使用自然、简洁、专业的简体中文，避免照搬英语语序。

## 编辑原则

- 直接面向学习者时使用“您”，主语明确时不重复“我们”或“我们的”。
- 保留产品名、代码、命令、标识符、文件路径、URL、API 字段、模型 ID、占位符和引用文献的英文标题。
- `Blueprint` 始终保留英文。普通技术说明中的 `prompt`、`workflow`、`runtime` 分别译为“提示词”“工作流”“运行时”，代码和界面原文除外。
- 同一个概念在正文、可运行示例、界面文本和 SVG 图中保持一致。只有语义确实变化时才使用不同译法。
- 中国本地化的学习者文本不推荐 Codex 或 Claude Code；需要泛指时统一使用英文 `coding agent`。

## 质量门禁

生成器只负责草稿。必须同时运行仓库的资源、结构、SVG、构建和浏览器检查，以及 DLI 的共享翻译审查。只有在 Localization Studio 中逐段对照英语源文并检查最终渲染结果后，才能接受 source/target hash。

```bash
python3 scripts/validation/localization_audit.py --locale zh-CN
python3 scripts/validation/locale_resource_audit.py
python3 scripts/build/assemble_locale_overlay.py --self-test
```

当前本地交付有意不接受审阅 hash，方便课程所有者先检查译文。
