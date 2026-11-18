# MessyShaders

A modpack-specific high-performance Iris shader project for Minecraft 1.21.1.

**Status:** Research and baseline packaging, NOT YET a new custom shader renderer.

Supplied comparison archives:
- MakeUp Ultra Fast 9.6 (lightweight shadow/effect baseline).
- E-Lite 5.1.3 (LGPL-3.0 source foundation).
- Complementary Reimagined r5.10 (visual/lighting feature reference; custom licence).
- Luxium 2.8.4 pre-alpha decompiled (architecture-only reference; custom licence; 1.20.1).

See [the fast-path audit](docs/FAST_PATH_AUDIT.md).

## Experimental high-performance RGB branch

**The first experimental build is NOT a complete shader.** This branch contains an E-Lite-derived shader ZIP with a thirteen-colour palette, coloured emitter surfaces, a bounded fake coloured handheld-light effect, original warm/cool grading and automated import of the MIT-licensed Euphoria block/item light-source classifications.

**Already built:** GitHub Actions workflow **Experimental RGB shader build** generates a valid shader ZIP as a downloadable `messyshaders-rgb-experimental` artifact. It runs four builder tests and packages E-Lite + the classification generator; it does not run Iris/GLSL compilation or in-game FPS measurements. The Euphoria reference data is pinned in CI and MIT permission notice is bundled with the archive.

**Not yet implemented:** occluded multi-source world RGB lighting, independent dynamic dropped items/entities/projectiles, IntegratedPBR+-equivalent built-in materials, and GPU-cache/shadow ideas from Luxium. The RGB look of this alpha should not be mistaken for proper coloured world light.

Build locally with Python 3 and the supplied E-Lite ZIP:

```sh
python3 tools/build_fast_rgb.py
# To include optional MIT Euphoria classification data:
python3 tools/build_fast_rgb.py --euphoria-root external/euphoria-properties
```

Read [renderer architecture and benchmark gates](docs/RENDERER_ARCHITECTURE.md). Luxium is used as an **architecture-only reference**, never by copying proprietary decompiled code.

Run `python3 tools/audit_packs.py` to inspect the exact supplied ZIPs. It writes a comparison report and packages an **unmodified E-Lite baseline** under dist/ for future benchmark controls. It does not incorporate proprietary code from the comparison packs.

**Goal:** Full modded RGB lighting, dynamic emissive sources, Complementary-like color/material appearance, IntegratedPBR+-style built-in materials, MakeUp/E-Lite-grade fast shadows/light shafts, Voxy support and shader-compatible entity effects. First measure and establish the fastest full-feature path; settings menus come later.
