# MessyShaders

A modpack-specific high-performance Iris shader project for Minecraft 1.21.1.

**Status:** RGB light visually confirmed by tester; new moving-light and generated-PBR additions are not yet runtime validated or benchmarked.

Supplied comparison archives:
- MakeUp Ultra Fast 9.6 (lightweight shadow/effect baseline).
- E-Lite 5.1.3 (LGPL-3.0 source foundation).
- Complementary Reimagined r5.10 (visual/lighting feature reference; custom licence).
- Luxium 2.8.4 pre-alpha decompiled (architecture-only reference; custom licence; 1.20.1).

See [the fast-path audit](docs/FAST_PATH_AUDIT.md).

## November 19 Iris / Neo-Voxy runtime diagnostics

The user-provided Minecraft 1.21.1 log identified three **actual** Neo-Voxy shader compatibility errors in the first integrated build: duplicate `messyRgbHistoryASampler`/`BSampler` declarations, use of `texture3D()` in core GLSL, and an unavailable `endFlashIntensity` uniform on Minecraft 1.21.1. The corrected shared RGB helper now lets Neo-Voxy inject its own samplers, uses `texture()` for Voxy/Colorwheel GLSL, and gates the version-specific uniform in `voxy.json`.

**Lite LOD:** The Neo-Voxy 0.5.0-beta fork requires **both** `voxy_opaque_lite.glsl` and `voxy_translucent_lite.glsl` in every dimension directory, each with an identical `VOXY_LITE_CONTRACT api=1` marker. This build supplies that pair. The **00:57:18 `MISSING_PROGRAMS` message in `latest(20261119-010029).log` occurred when the user switched to `ComplementaryReimagined_r5.9.3.zip`**, not while MessyShaders was active. At 00:54, 00:58 and 00:59 MessyShaders had positively loaded the Lite pair. Complementary r5.9.3 does not provide an optional Neo-Voxy Lite pair in the active pack directory, so the fallback warning is expected there. The Lite opaque variant skips distant glossy lighting; water/translucent shading is now adjusted to match E-Lite's near-water path.

**Generated normals:** The previous conservative fix made the effect nearly imperceptible: luminance gradients were suppressed and scaled to 24%, then daylight changes were capped at 12% after more attenuation. The new path uses the same two atlas texture taps with stronger, still-clamped gradients and modulates **directional irradiance only** between 0.60 and 1.50 times normal. It does not multiply ambient illumination or coloured emissive lighting and still preserves authored LabPBR maps. Normal Strength 0 disables the bump; 1 should visibly alter stone/grain relief in direct light; 4 is an intentionally exaggerated stress test. This is *not* full Complementary IntegratedPBR+ material classification.

**Water LOD transition:** The earlier Voxy path used a linear water-absorption gap and different underwater tinting while nearby E-Lite water squared its depth gap. The new shader uses Voxy's **opaque** depth behind water, matches the same squared attenuation and tint, and tapers near waves out over the last 64 blocks while distant Voxy waves return over the first 64 LOD blocks. The transition uses the square chunk boundary, not a radial camera-distance threshold. This avoids another shader pass or opacity dithering, but the screenshot seam still needs an actual game test. The idea is informed by Complementary's LOD-aware water handling; no Complementary source is copied.

**Minecraft 1.21.1 parser noise:** Iris 1.8.14-beta.1 cannot resolve `BIOME_PALE_GARDEN` (introduced after 1.21.1); the custom uniform is now fixed to zero on older versions. The `MESSY_COATED_TEXTURES` toggle now has an explicit `#ifdef` guard for Iris's menu option collector.

**Colorwheel:** The same log also shows Flywheel falling back from `colorwheel:indirect` to `flywheel:off` during pipeline reloads. No specific Colorwheel shader compile error is present in that log; this remains to be verified independently after Neo-Voxy compiles. Do not assume Flywheel is accelerated because the shader ZIP contains Colorwheel programs.

GitHub Actions now additionally compiles the actual shared RGB sampler helper in a **GLSL 430 core** harness with Neo-Voxy-style injected uniforms. This catches the precise duplicate-sampler/legacy-function failures that older offline compatibility-only tests missed.

## Temporal RGB, generated normals, Colorwheel + Voxy (November 19 update)

**Temporally stable dynamic coloured lights:** the original 48³ source/occupancy volumes and six diffusion iterations remain. A seventh compute stage (`prepare_g.csh`) reprojections previous RGB illumination using integer camera movement. Two persistent RGBA16F history volumes alternate reads and writes. New light appears immediately; disappearing/moving lights fade more smoothly rather than resetting entirely. Increased memory: ~1.77 MiB plus a single 48³ compute pass. This is a modest temporal filter, not Complementary's full ACT implementation, and **GPU timings have not been measured**.

**Generated Normal Strength now changes diffuse illumination:** computed atlas normals feed the visible surface lighting directly on all terrain/block material paths even without high-quality reflections. Sun and moon directions come from their existing view-space uniforms, and the effect remains zero at strength 0. Prior UV-shift/parallax code is still removed. Coated Textures remains a separate inexpensive procedural detail control. If you enable authored LabPBR maps, their normals take precedence over generated normals.

**Native Colorwheel support:** `clrwl_gbuffers.vsh/.fsh`, `clrwl_shadow.vsh/.fsh`, and `colorwheel.properties` are bundled with the shader. Colorwheel material processing uses `clrwl_computeFragment`; one OIT coefficient buffer corresponds to E-Lite's actual scene target `colortex1`. The render program consumes the **same temporally filtered RGB field** as vanilla terrain and can classify eligible Create/Flywheel shadow geometry as light sources. You should not need to merge another shader ZIP for the program files, though rendering correctness must be tested with your actual Colorwheel build. Verify `/flywheel backend` reports `colorwheel:instancing`.

**Native Voxy support retained:** existing Voxy geometry shaders, shadows, fog, depth handling, JSON layouts and native texture shading are preserved. Opaque **and translucent** Voxy fragments can sample the same RGB history inside the nearby 48³ field; Voxy LOD lighting beyond that field is unchanged. The shader registers two history samplers and `frameCounter` in E-Lite's shared `voxy.json`, while suppressing duplicate sampler declarations in the fragment source. It does **not** mix into Neo-Voxy, Voxy, Iris or Minecraft, allocate distant RGB voxels, change queue/RAM defaults, or claim all LOD chunks have propagated RGB light.

**Validation:** GitHub Actions tests the generated ZIP and compiles normal G-buffer, Colorwheel wrapper (offline mock for Colorwheel's injected material callback), shadow and compute shader stages. These checks cannot reproduce your full Iris + Neo-Voxy + Colorwheel runtime or measure GPU frame times. Please check shadow/lighting alignment on rotating Create contraptions, moving XP orbs, stone normals at different sun angles, and the Voxy near/far seam. This branch remains experimental.

## Expanded Euphoria light coverage and raised/coated textures

The latest experimental ZIP adds a controlled import from the **Euphoria Patches MIT entity classification data**. The pinned catalogue currently contributes 230 modded entity candidates across 20 eligible lighting groups, while retaining E-Lite's original IDs. Additional classified vanilla categories include allay, vex, experience orb, enderman, drowned, stray, trident, bogged, creaking, parched, zombie nautilus, spectral arrow, eye of ender, and the **entity-flame renderer**. It can also treat a dropped item rendered using one of our classified block IDs as a light.

**Important qualification:** Classification is broad; some modded entities grouped with luminous vanilla mobs are not themselves emissive. The technique works only for sources visible to the shadow-rendering pass, and cannot infer NBT data such as whether an ordinary arrow is burning. Flame effects are supported through their actual `entity_flame` render classification when Iris exposes that pass. This is not perfect Complementary r5.10 parity.

Texture controls under **Messy Features**:
- **Generated Normal Strength:** one conservative surface-bump control using texture-local luminance differences. Suppresses pixel-art noise and aggressive gradients; applies automatically to modded terrain/block textures.
- **Coated Textures / Coating Strength:** a very inexpensive, nonreflective procedural micrograin coating over albedo. This is *not* a clearcoat specular layer. No extra texture sample is required for the coating itself.
- **Removed:** the faulty one-step parallax/relief option and the displaced voxel-light sample, which could produce block-size patches and UV artifacts. Actual height/POM remains available only through separately supported LabPBR maps.
- Authored LabPBR maps retain precedence over generated normals. The coating is independently configurable.

The intensity tier of dynamic sources is now encoded in the same light-volume voxel ID: tiny XP orbs/spectral arrows receive weak illumination; blazes and flame sprites are brighter; placed blocks stay full strength. A soft energy gate reduces very weak long-distance spill. No extra 3D volume or diffusion pass has been added. **GPU cost and visual correctness still need in-game measurement.** Compare Coated Textures and Generated PBR independently.

These implementations are independently written. No code from Complementary's restricted shader sources was copied; Euphoria's classifications are MIT licensed and their notice is bundled.

## Experimental moving lights + generated PBR (new)

The build now includes **experimental dynamic coloured lights** using Iris shadow-stage `currentRenderedItemId` and `entityId`. Dropped/rendered items classified by Euphoria's MIT-licensed item light list and selected vanilla luminous entities (blaze, glow squid, magma cube, end crystal, fireballs and fireworks) write into the **existing** RGB voxel volume. Placed fire, soul fire and lava are also classified as coloured emitters. It requires entities to be rendered in the shadow pass. This is not full Complementary r5.10 dynamic-light parity; it does not yet detect arbitrary burning mobs, particle light emission or mod-specific moving bosses.

The **independent auto-material prototype** generates normals and roughness from the actual sampled atlas texture, including modded terrain and block textures, without generating resource-pack files. It uses **two additional neighbouring texture samples per terrain/block fragment** and existing tangent data. A vanilla metal-material classification can still drive metallic behaviour, but arbitrary textures are **not automatically classified as the correct material**. This is IntegratedPBR+-style behaviour, not a full port or full feature parity. Existing LabPBR resource-pack normal/spec maps take priority.

In shader settings find **Messy Features** (on the main page) with toggles for `MESSY_DYNAMIC_EMITTERS` and `MESSY_IPBR` plus normal-strength selection. Both are enabled initially for comparison; disable individually to profile GPU cost.

**Please test**: an orange dropped torch next to a cyan sea lantern, blaze/glow squid lighting while moving, burning tree vs unlit foliage, modded ore/stone textures with generated detail, and on/off frame-time changes. There has been no in-game Iris validation or GPU benchmark of the new features yet; these are validated by unit tests and offline GLSL compilation only.

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
