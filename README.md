# MessyShaders

A modpack-specific high-performance Iris shader project for Minecraft 1.21.1.

**Status:** Research and baseline packaging, NOT YET a new custom shader renderer.

Supplied comparison archives:
- MakeUp Ultra Fast 9.6 (lightweight shadow/effect baseline).
- E-Lite 5.1.3 (LGPL-3.0 source foundation).
- Complementary Reimagined r5.10 (visual/lighting feature reference; custom licence).
- Luxium 2.8.4 pre-alpha decompiled (architecture-only reference; custom licence; 1.20.1).

See [the fast-path audit](docs/FAST_PATH_AUDIT.md).

Run \`python3 tools/audit_packs.py\` to inspect the exact supplied ZIPs. It writes a comparison report and packages an **unmodified E-Lite baseline** under dist/ for future benchmark controls. It does not incorporate proprietary code from the comparison packs.

**Goal:** Full modded RGB lighting, dynamic emissive sources, Complementary-like color/material appearance, IntegratedPBR+-style built-in materials, MakeUp/E-Lite-grade fast shadows/light shafts, Voxy support and shader-compatible entity effects. First measure and establish the fastest full-feature path; settings menus come later.
