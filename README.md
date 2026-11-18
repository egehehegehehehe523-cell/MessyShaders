# MessyShaders

A modpack-specific high-performance Iris shader project for Minecraft 1.21.1.

**Status:** Experimental RGB lighting renderer; not Iris-tested or performance-qualified.

Supplied comparison archives:
- MakeUp Ultra Fast 9.6 (lightweight shadow/effect baseline).
- E-Lite 5.1.3 (LGPL-3.0 source foundation).
- Complementary Reimagined r5.10 (visual/lighting feature reference; custom licence).
- Luxium 2.8.4 pre-alpha decompiled (architecture-only reference; custom licence; 1.20.1).

See [the fast-path audit](docs/FAST_PATH_AUDIT.md).

## Experimental high-performance RGB branch

**The new world-light prototype is NOT a complete shader.** It combines the existing E-Lite coloured held-light and visible emitter surfaces with a **48×48×48 world-space voxel RGB volume** collected from the original shadow draw. Six lightweight compute diffusion steps extend placed light to neighbouring geometry. Blocks can approximately obstruct light; complex translucent geometry and offscreen chunk coverage are unverified. This version still includes the MIT-licensed Euphoria classification importer.

**Already built:** GitHub Actions workflow **Experimental RGB shader build** generates a valid shader ZIP as a downloadable `messyshaders-rgb-experimental` artifact. It runs four builder tests and packages E-Lite, the Euphoria classification generator and an experimental Iris custom-image/compute propagation implementation; it does not run Iris/GLSL compilation or in-game FPS measurements. The Euphoria reference data is pinned in CI and MIT permission notice is bundled with the archive.

**Not yet implemented:** verified Iris rendering, exact/complete occlusion, independently tracked dropped-item/entity/projectile lights, IntegratedPBR+-equivalent built-in materials, and dirty-region GPU caching. World RGB requires Iris custom images + compute (OpenGL 4.3) and an existing working shadow pass. **The Overworld is the initial test target; the Nether lacks E-Lite shadow programs.** GPU overhead, correctness and Voxy transitions still need measurement.

Build locally with Python 3 and the supplied E-Lite ZIP:

```sh
python3 tools/build_fast_rgb.py
# To include optional MIT Euphoria classification data:
python3 tools/build_fast_rgb.py --euphoria-root external/euphoria-properties
```

Read [renderer architecture and benchmark gates](docs/RENDERER_ARCHITECTURE.md). Luxium is used as an **architecture-only reference**, never by copying proprietary decompiled code.

Run `python3 tools/audit_packs.py` to inspect the exact supplied ZIPs. It writes a comparison report and packages an **unmodified E-Lite baseline** under dist/ for future benchmark controls. It does not incorporate proprietary code from the comparison packs.

**Goal:** Full modded RGB lighting, dynamic emissive sources, Complementary-like color/material appearance, IntegratedPBR+-style built-in materials, MakeUp/E-Lite-grade fast shadows/light shafts, Voxy support and shader-compatible entity effects. First measure and establish the fastest full-feature path; settings menus come later.
