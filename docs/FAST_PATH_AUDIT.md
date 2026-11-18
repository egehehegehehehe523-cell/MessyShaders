# Fast-path selection — 18 November 2026

**Target:** NeoForge 1.21.1, Iris, Neo-Voxy, large GeckoLib crowds and many modded lights. Priority is the fastest practical **complete** implementation, not a low-feature preset. Settings menus deferred.

## Findings, from inspected source

**E-Lite 5.1.3 / MakeUp 9.6:** The exact supplied E-Lite ZIP (386 files) contains no dynamic-light or voxel-propagation signals in the shader source audit. E-Lite's shaders/lib/config.glsl selects a single blocklight tint CANDLE_COLOR by BLOCKLIGHT_TEMP, then shaders/src/light_vertex.glsl uses CANDLE_BASELIGHT. This is cheap but not full per-emitter RGB lighting. COLORED_SHADOW concerns translucent shadows, not individually-colored placed light sources. Existing paths for efficient screen-space/volumetric godrays, shadows, emissives, LabPBR and Voxy are valuable starting points; do not rebuild them without evidence.

**Complementary Reimagined r5.10:** Released November 18, 2026. New Dynamic Colored Lighting reportedly enables dropped items and special entities to cast colored light; held lighting was also reworked. Source-level verification: the new item/entity sources are injected into the EXISTING Advanced Color Tracing (ACT) voxel volume during the shadow pass. COLORED_DYNAMIC_LIGHTING is defined only when COLORED_LIGHTING_INTERNAL > 0 and ENTITY_SHADOW >= 1 (shaders/lib/common.glsl). shaders/program/shadow.glsl marks the extra item/entity emitters; shaders/program/shadowcomp.glsl recovers their source IDs and feeds the existing light/flood-fill pipeline. Thus it can be incremental when ACT is already enabled, but it is NOT a cheap standalone colored-lighting algorithm and still incurs ACT's base cost. Neither the release notes nor static inspection establish frame-time figures. Complementary's coloration, IntegratedPBR+ and broad Euphoria-supported light catalogue are design targets, NOT code to copy.

**Luxium 2.8.4 pre-alpha:** targets Minecraft 1.20.1 Forge/Fabric and explicitly blocks Iris/Oculus. Its independently observed ideas include cached local-light and shadow atlases, dirty section invalidation, a screen-tiled local-light list, bounded dynamic shadow updates and Kawase-style bloom. Those may be reusable **conceptually** only, and their speedup is unproven for our scenes. Source is decompiled and under a proprietary custom licence; do not copy or redistribute.

**Additional reference:** Just Colored Lighting advertises cheap colored block/dynamic lights, automatic mod-light detection and PBR. Investigate its techniques and license; compare actual GPU time rather than accepting marketing claims.

## Proposed technical comparisons

1. **Control:** original E-Lite full-feature rendering and blocklight tint. A correct performance baseline, not a completed RGB implementation.
2. **Sparse dynamic RGB:** per-source colors, a bounded/tiled light list, event-driven dirty updates and shared fullscreen lighting instead of a pass per source. Check held/dropped items, entities, many active effects, unsupported-source fallback.
3. **Static RGB volume:** compare a compact camera-relative light volume with incremental section updates against voxel flood-fill. Test occlusion, caves and offscreen lights; don't implement visible-emitter-only shortcuts.
4. **Shadows/emissives/PBR:** reuse E-Lite/MakeUp low-cost paths, then selectively integrate independently written material rules and Euphoria-like mod light classifications, plus accurate near/far Voxy depths.

## Validation and licensing gates

No claims of being fastest until we measure repeated GPU pass times, frame times and 1% lows in matched 1/50/500-light caves, multi-colour lantern scenes, 500 animated mobs, day and night, NTM effects and Voxy transitions. Check artifacts, entity shadows, PBR reflective surfaces, multi-light interactions, moving emitters, chunk reload and changed blocks.

E-Lite and MakeUp are LGPL-3.0 with attribution/source obligations. Complementary and Luxium have restrictive redistribution terms. The pack builder handles **only E-Lite**; it does not transplant their code. Euphoria property data needs its own licence review before any copying.

The source audit in tools/audit_packs.py checks the exact archives uploaded to this repository and builds an unchanged E-Lite baseline ZIP. It does not compile shader GLSL or benchmark GPU performance.

Sources:
- https://github.com/EntokitoDezonze/E-LITE-shaders
- https://github.com/javiergcim/MakeUpUltraFast
- https://www.curseforge.com/minecraft/shaders/complementary-reimagined/files/9687811
- https://github.com/Bernard2806/Luxium-decompiled/tree/2.8.4-pre-alpha
- https://modrinth.com/shader/just-colored-lighting

Additional exact r5.10 source reference: https://github.com/ComplementaryDevelopment/ComplementaryReimagined/commit/d0c7cd99b8459acdd10011261a8270fce888be8f
