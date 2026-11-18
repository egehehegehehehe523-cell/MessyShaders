# MessyShaders: fastest *complete* renderer architecture

Target: NeoForge 1.21.1 + Iris + Neo-Voxy, heavy animated entities and many modded emissive lights, GPU-bound hardware. The objective is **full-feature performance**, not a featureless benchmark preset.

**Status as of 18 November 2026:** The experimental RGB ZIP is a real, buildable **shader pack archive**, but it is only the **classified emitter and coloured held-light prototype**. Unit tests/packaging pass. No Iris GLSL compile, test-world render, GPU timing or full RGB world lighting has been confirmed.

## Reference ownership and licences

- **Luxium 2.8.4 decompiled:** architectural inspiration for bounded per-tile light lists, shadow/light caching and dirty-section invalidation; cannot transplant code or distribute decompiled renderer. Its mod is not a 1.21.1 Iris shader pack; the supplied 1.20.1 version blocks Iris/Oculus. Claims of superiority need measured matched workloads.
- **E-Lite 5.1.3 and MakeUp UltraFast 9.6:** LGPL-3.0 shader sources and performance primitives; preserve attribution and complete corresponding source under the LGPL.
- **Complementary Reimagined r5.10 / Euphoria Patches shader logic:** look-and-feature reference only. Its ACT voxel light volume is not a zero-cost shortcut to RGB light; do not copy restrictive code.
- **Euphoria propertiesFiles:** MIT-licensed source **classification data** may be processed into generated block/item mappings. The independent palette and RGB math remain MessyShaders' own code. Include the original MIT notice when packaged.
- **IntegratedPBR+** is a *target feature/behaviour*. Replicate using independently authored vanilla material assignment, not copied Complementary GLSL. Preserve E-Lite's LabPBR path as resource-pack option.

## Render plan

### Phase A: correct cheap E-Lite base (partially started)
- Keep base shadow/light shafts/bloom/AA/reflections/Voxy geometry passes and optimise measured hotspots only.
- Use a different colour grade with warmer highlights, cooler shadow tones, configurable day/sunset/night/sky/fog colours. Grading must not add a new fullscreen pass.
- Add block/item/entity classification tables as **data**, not branches in the fragment shader. Missing/unregistered modded sources fall back to neutral lighting.
- The initial prototype colours source surfaces and a small fake held-light radius. It **does not** fulfil world RGB; explicit fallback, not the end state.

### Phase B: full coloured RGB world lighting (not yet implemented)

Compare these implementations with *identical features*:

1. **Sparse source atlas + bounded tile evaluation** (candidate fastest for dynamic emitters):
   - Gather nearby light sources with stable IDs and world-space positions, colour, intensity/radius, type and active state.
   - Divide camera view into screen tiles and bin light IDs; evaluate only each tile's bounded list during existing deferred lighting (avoid N passes for N lights).
   - Source list updates only on move, spawn, despawn, colour/intensity change, chunk changes; do not rebuild it from every entity every frame.
   - For natural looking light, sample a compact occlusion representation (nearby depth or world-space voxel occupancy), measure cost and artifacts.
   - Shaderpack-only implementation must have a **supported source-discovery path**. Iris shaderpack property IDs identify rendered materials but do **not** inherently supply XYZ positions of every off-screen placed block or moving entity. Visible-emitter-only hacks fail the off-screen test. A narrowly scoped helper mod may be needed if Iris cannot expose source updates cheaply and reliably; verify integration before choosing it.

2. **Camera-relative world RGB volume** (candidate for many static emitters):
   - Collect emissive geometry and occupancy in a bounded volume. Use a compact format and separate occupancy/emission from diffusion.
   - Rebuild only changed regions if API/synchronisation permits, not a whole large 3-D light field each frame.
   - Conserve memory/bandwidth; profile multiple volume sizes/precisions. Never infer cheaper from resolution alone.
   - Real overlapping colours, caves and lights behind camera must work. Use an explicit graceful fallback outside volume instead of fake screen-space halos.
   - If using Iris custom 3D images/compute shader facilities, validate against **the actual supported Iris build** and Minecraft 1.21.1. Native Luxium GPU caching code cannot run as shaderpack code.

3. **Hybrid** (likely practical, not a proven winner): sparse dynamic emitters + incrementally maintained static RGB field, merged before material shading, with one shared light accumulation step. Avoid adding RGB highlights and again re-lighting the same surface in a different pass.

**Acceptance:** Red and cyan emitters overlap into plausible coloured light on nearby *other* surfaces; placing an opaque wall blocks the light; torches continue lighting when moved offscreen; block sources survive chunk reload; moving hands/projectiles/entities update smoothly; no flicker at render distance. Tests include coloured lights in caves, terrain transitions and submerged scenes.

### Phase C: dynamic colored light roster (not yet implemented)
- Use Euphoria MIT classification as the supported modded source taxonomy (block, item and entity categories). Import carefully and avoid **ambiguous material classification collisions** (block IDs used by the original renderer may also convey PBR/waving/other functionality).
- Source **detection** is separate from shader colours. A line in `item.properties` cannot cause a dropped-item *world position* to be emitted without a renderer path that reports it.
- Support held/offhand items, dropped items, projectiles (including custom NTMBullets), moving entity features, fire/explosion/nuclear flashes and HBM lights. Multi-emitter limits must be explicit, deterministic and gracefully degraded.
- Bounded work; intensity decay, temporal stability and prioritisation by screen influence rather than every source as a dynamic shadow caster.

### Phase D: materials, appearance and Voxy (not yet implemented)
- Independently authored built-in roughness/metallic/porosity/emissivity rules for vanilla and selected modded blocks as IntegratedPBR+-equivalent behaviour.
- Preserve explicit LabPBR texture maps; material rules must not override resource pack-supplied maps unexpectedly.
- Complementary-inspired but original sky/fog/water palettes, filmic tone curve, distinctive restrained warm/cool contrast. Expose simple colour controls *after* implementation/perf validation.
- Neo-Voxy geometry depth, near/far blending and disocclusion; don't modify Voxy or Minecraft unnecessarily. Ensure particle/entity depth ordering (NTM and world bosses) remains correct.

## Benchmark design

Keep effects comparable across all candidates, not 'Luxium without PBR vs Complementary with PBR'.

Scenes:
- 1, 50, 500 independent colored emitters; placed/held/moving; static and camera motion; cave with turns, water, near/far Voxy boundary.
- Dense animated GeckoLib crowds (e.g. 500 mobs), with local emissive projectiles/particles.
- Full resource-pack LabPBR, emissive/metallic materials, day/night, rain, fog, glowing ores, NTM/HBM explosions.
- Test initial compile/startup, frame-time median/p95/p99, GPU pass timings, 1% lows, VRAM and texture bandwidth, artifacts and source-update latency.
- Test baseline E-Lite with identical effect budget, full Complementary ACT/dynamic lighting (if licensed/available), E-Lite+RGB candidates, and MakeUp. Luxium 1.20.1 is not an apples-to-apples 1.21.1 Iris measurement.

## Minimal safe next implementation gate

Before declaring RGB 'working':
1. Get the experimental pack compiling in Iris 1.21.1 and check `latest.log` on the target GPU.
2. Decide whether complete source position capture is possible without a helper. Reject any approach depending exclusively on visible surfaces.
3. Prototype true multi-source light affecting neighbouring surfaces **with occlusion**. Benchmark the actual GPU cost.
4. Add independent IPBR-equivalent material rules, then optimize colour, sky/shadows and volumetrics.

Don't raise Neo-Voxy snapshot/queue/RAM defaults to compensate for shader-side work.
