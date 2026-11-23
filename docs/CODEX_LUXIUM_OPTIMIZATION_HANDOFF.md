# Codex handoff — Luxium-inspired *measured* fast paths

**23 November 2026.** This is an implementation brief, not a request to port
Luxium or to restart the old experimental RGB renderer. The user wants the
fastest **complete** E-Lite-based shader for a GPU-bound Minecraft 1.21.1
modpack, with no lost materials, shadows, reflections, lighting, Voxy or mod
compatibility. Optimize observed GPU bottlenecks; no unsupported speed claims.

## 1. Freeze the accepted baseline

- **Working branch:** `feature/elite-pbr-voxy-fog` in
  [`egehehegehehehe523-cell/MessyShaders`](https://github.com/egehehegehehehe523-cell/MessyShaders/tree/feature/elite-pbr-voxy-fog).
- **Accepted build:** `MessyShaders-E-Lite-PBR-Voxy.zip`, Library version **15**;
  source builder `tools/build_elite_materials_voxy.py`; latest successful
  [Actions run 45085868944](https://github.com/egehehegehehehe523-cell/MessyShaders/actions/runs/45085868944).
- **Water is DONE.** The tester confirms Voxy/normal water is consistently
  blue and brilliantly blended with its proper reflections/transparency. A
  tiny geometry seam appears in Complementary too and is explicitly accepted
  as a Voxy issue. Retain `MESSY_WATER_LIGHT_HANDOFF`, shared depth/opacity,
  source-over blending, diagnostics, reflection and cloud-depth handling.
  Don't attempt another water fade, darkness multiplier or postpass.
- Preserve automatic atlas-normal PBR, authored LabPBR priority, the optional
  entity material path, Colorwheel's actual draw/shadow programs, Voxy fog and
  its options, and the Voxy cloud occlusion fix. Do not replace this pack with
  an old RGB experiment just because the old branch has more optimization code.
- **Branch discipline:** create a separate optimization branch from this
  working baseline; keep it easy to abandon. Do not merge experimental RGB
  commits wholesale. The `feature/luxium-inspired-fast-rgb` docs and code are
  references/history, **not** the production source of truth.

## 2. What was tried, with actual outcomes

| Experiment / historical implementation | Status / failure | What Codex must learn |
| --- | --- | --- |
| 48³ camera-relative RGB illumination; voxel capture, diffusion and temporal history | Experimental. Some RGB did render, but GPU cost and multi-source correctness were **never demonstrated**. | A finite RGB field is not a free or complete substitute for real block/entity source positions. |
| Fused seed/propagation plus 8-bit RGB volumes | Potential bandwidth/dispatch saving, but **no reliable GPU A/B**. | Measure dispatch, image clears, occupancy reads, precision artifacts and camera-motion banding separately. |
| Shared-memory 8×8 seed tile with halo (#95) | **Withdrawn:** tester reported coloured world illumination disappearing. | Source-level compilation did not prove the code ran correctly in Iris on the user's driver. Do not revive without a minimal GPU correctness test. |
| Simplified bloom/SSR and water/SSR edge fades (#95–96) | **Withdrawn:** water/reflections distorted or disappeared. | Avoid global post-process substitutions and speculative SSR alterations; preserve the accepted water renderer. |
| Moving-light vertex-position capture | A previous matrix-origin error attached light to the player; vertex sampling fixed this partially, but animated surfaces are not stable entity centres. | A rendered entity/category ID is **not** a stable XYZ source. Test independently moving emitters. |
| Temporal light-volume reuse | An extra history pass can stabilize flicker, but increases texture/pixel work; speed unmeasured. | Don't confuse visual temporal accumulation with CPU/GPU caching or dirty-section reuse. |
| Luxium's local light/shadow caches | **Not ported**: Luxium is a renderer mod with CPU-side change data and different renderer ownership. | An Iris shader ZIP cannot infer every block/chunk update or own Minecraft's render draw lists. |

Prior writeups (experimental branch only):
[`LUXIUM_PORTABLE_FAST_PATHS.md`](https://github.com/egehehegehehehe523-cell/MessyShaders/blob/feature/luxium-inspired-fast-rgb/docs/LUXIUM_PORTABLE_FAST_PATHS.md),
[`FAST_PATH_AUDIT.md`](https://github.com/egehehegehehehe523-cell/MessyShaders/blob/feature/luxium-inspired-fast-rgb/docs/FAST_PATH_AUDIT.md),
[`RENDERER_ARCHITECTURE.md`](https://github.com/egehehegehehehe523-cell/MessyShaders/blob/feature/luxium-inspired-fast-rgb/docs/RENDERER_ARCHITECTURE.md), and
[`OPTIMIZATION_AND_VOXY_CHECKLIST.md`](https://github.com/egehehegehehehe523-cell/MessyShaders/blob/feature/luxium-inspired-fast-rgb/docs/OPTIMIZATION_AND_VOXY_CHECKLIST.md).
Those documents describe older experiments; reconcile them with the v15
production baseline before changing anything.

## 3. Proposed engineering sequence

**Stage A — Measure before writing code (first Codex task).**

1. Inventory the current v15 render graph: shadow map, ambient/cloud/fog,
   water/refraction/SSR, bloom, generated normal taps, transparency, Colorwheel,
   Voxy composite and postpasses. Record which run in which dimension/program.
2. Obtain repeatable **GPU pass timings** using the user's actual Minecraft
   1.21.1/Iris/Neo-Voxy stack and GPU. Separate GPU-bound from CPU-bound cases;
   FPS alone is inadequate. No FPS claims from CI or synthetic GLSL counts.
3. Measure baseline median and p95/p99 frame times, 1% low FPS, GPU frame ms,
   VRAM use and significant pass times. Record RD/LOD, resolution, settings,
   mod list, scene, day/weather and shader preset.
   **If Codex does not have the user's GPU/game available, prepare a small
   reproducible profiling checklist and request the capture. Do not invent
   measurements, substitute CI timings or declare an optimization winner.**
4. Rank cost centres by **measured GPU time**. Choose **one**; do not implement
   multiple cross-cutting changes before the first A/B.

**Stage B — Low-risk shader-only experiments (in measured priority order).**

| Candidate | Isolated implementation / gate | Regression to watch |
| --- | --- | --- |
| Pixel masks and early exits | Skip expensive SSR/ray work only for proven non-reflective, depth-occluded or offscreen contributors within the **existing** shader path. | Missing water/metal reflections; earlier #95–96 failures. |
| Normal sampling budget | Profile the four-tap generated PBR normals. Test current distance/footprint cutoff before changing tap count or authored LabPBR paths. | Texture relief disappearance, gravel aliasing and PBR-on-entity parity. |
| Shadow filtering | Skip filter taps where effective shadow/sky contribution is demonstrably zero; do not touch Iris shadow-map allocation/cascades. | Create/Colorwheel machine shadows, foliage cutouts and sun angle. |
| Clouds / volumetrics | Gate samples behind opaque Voxy depth and empty-density regions; measure existing raymarch cost first. | Clouds in front of mountains, sky holes, water cloud reflections. |
| Bloom/godrays | Reduce *redundant* taps or reuse verified intermediates, without extra full-screen passes. | Source glare missing, reflection distortions, light shafts/water parity. |

For each candidate: add a **default-off** named switch; compile and run it in
isolation; compare both modes with identical features and camera position;
record the GPU delta and screenshots; revert if the difference is inside noise
or causes artifacts. Enable by default only after the tester accepts it.

**Stage C — Only after measurements, assess a more ambitious lighting design.**

- Dynamic per-screen-tile lists require actual world-space positions, stable
  source identities, RGB/intensity/radius and an Iris-compatible upload path.
  Classifying a visible material ID is insufficient for offscreen torch data.
- Static RGB caches need chunk/section dirty notifications, generation tags,
  eviction, dimension/reload invalidation and synchronization. A stale volume
  when the camera pauses is a **bug**, not a cache optimization.
- If those events cannot be provided through supported APIs, write a **small
  separate client-helper proposal** and cost estimate; ask for authorization
  before implementing. No mixins into Neo-Voxy, Iris, Minecraft, C2ME/OpenCL
  or the current gameplay mods merely to claim a Luxium feature.
- Keep static and moving emitters separate, bound total light work, and
  compare a hybrid architecture against the actually working baseline. Do
  not assume more GPU compute is faster than E-Lite's ordinary blocklight.

## 4. Mandatory acceptance scenes and regression gates

Run both **baseline** and **candidate** under exactly the same settings:

- 1, 50 and 500 placed RGB sources; overlapping red/blue lights and an opaque
  wall. Place and break blocks, reload chunks, move the camera and stand still.
- An independently moving luminous entity/projectile, held/offhand items,
  NTMBullets and a dynamic source behind the player.
- Busy animated swarm (for example 500 GeckoLib mobs) with Colorwheel/Flywheel
  machines, dynamic shadows and shaders enabled.
- Rain/night/day transitions, ocean surface and underwater views, reflective
  PBR materials, sky/clouds against Voxy terrain and the accepted water seam.
- Overworld first, then Nether/End and any applicable modded dimensions.

**Ship only if** the pack loads on the target Iris version with no shader
compile errors, passes tests and **no regressions** in these scenes, and the
measured GPU gain clears normal run-to-run variance. A prettier screenshot,
lower theoretical shader instruction count, GitHub green check or higher FPS
in a feature-disabled preset does not establish a Luxium-class speedup.

## 5. Build and handoff discipline

- Clean pack build: `python3 tools/build_elite_materials_voxy.py`
- Unit tests: `python3 -m unittest discover -s tests -q`
- Check shader include/preprocessing variants and actual GLSL program
  compilation. Build/CI checks cannot guarantee Iris driver behaviour.
- Preserve the working ZIP/version separately. Provide a downloadable test
  build and a link to its passing GitHub Action; label it **experimental**.
- For each attempt report: changed file(s), baseline commit, toggle, exact
  scene/settings, GPU ms before/after, 1% low before/after, images/logs,
  correctness result, and a **keep/revert** recommendation.

## 6. IP / API boundaries and primary references

- **Luxium 2.8.4 pre-alpha** was a separate 1.20.1 renderer, incompatible
  with Iris/Oculus in its supplied build. Use architectural ideas only;
  **no copied decompiled code**, assets or derivative redistribution.
  Reference: [Luxium decompiled repository](https://github.com/Bernard2806/Luxium-decompiled)
  and its restrictive licence; do not use it as a compilable dependency.
- Iris supports custom images and compute shaders, but each extra pass/image
  must be timed and validated on the target version, including synchronization:
  [Iris ShaderDoc compute](https://github.com/IrisShaders/ShaderDoc/blob/master/passes/compute.md),
  [Iris custom images](https://shaders.properties/current/reference/buffers/custom_images/).
- E-Lite and MakeUp carry source/licence obligations. Complementary and
  Euphoria are appearance/classification *references*, not generic permission
  to copy their GLSL. Audit every imported data source and its attribution.

**Suggested prompt to Codex:** “Read `AGENTS.md` and
`docs/CODEX_LUXIUM_OPTIMIZATION_HANDOFF.md` on
`feature/elite-pbr-voxy-fog`. Start with Stage A: map and profile the current
v15 GPU render passes, recommend the single cheapest safe optimization, and
do not alter the accepted water renderer or merge old experimental RGB code.”
